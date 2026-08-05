import cheerio from 'assets://js/lib/cheerio.min.js';

// ===================== 站点配置 =====================
const appConfig = {
    siteName: "鱼塘社",
    siteUrl: "https://tv.yutangshe.com"
};

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

// 本站为 macCMS（苹果CMS）站点，模板 shortcut55，使用简洁 URL：
//   分类列表：/vodtype/{tid}-{page}.html        （page 可省略，默认 1）
//   详情页：  /voddetail/{id}.html
//   播放页：  /vodplay/{vodId}-{sid}-{nid}.html
//   搜索：    /vodsearch/{wd}-------------.html   （macCMS 13 段搜索 URL）
// 注意：站点的筛选页 /vodshow/{tid}-...-.html 实测返回"筛选页功能关闭中"，已被站长主动关闭。
//       因此本站唯一可用的"筛选"维度是「类型/子分类」切换（type_id 20-32），脚本据此提供类型筛选。
//       地区/年份/语言在详情页模板中不存在，无法提供这些筛选维度，故不展示假筛选项。

async function init(ext) {
    console.log("初始化爬虫:", appConfig.siteName);
}

// ===================== 分类列表 =====================
// 实测 type_id：主分类 20-23，电影子类型 24-32（站点的"类型"筛选即切换这些子分类 type_id）
const classList = [
    { type_id: "20", type_name: "电影" },
    { type_id: "21", type_name: "电视剧" },
    { type_id: "22", type_name: "综艺" },
    { type_id: "23", type_name: "动漫" },
    { type_id: "24", type_name: "动作片" },
    { type_id: "25", type_name: "喜剧片" },
    { type_id: "26", type_name: "科幻片" },
    { type_id: "27", type_name: "恐怖片" },
    { type_id: "28", type_name: "爱情片" },
    { type_id: "29", type_name: "剧情片" },
    { type_id: "30", type_name: "战争片" },
    { type_id: "31", type_name: "记录片" },
    { type_id: "32", type_name: "动画片" }
];

// ===================== 筛选配置 =====================
// 筛选页功能被站长关闭（/vodshow/ 返回"筛选页功能关闭中"），但子分类切换可用。
// 这里把"类型"做成一个筛选维度：值即各子分类的 type_id，切换时直接以该 type_id 重新拉取列表。
// 由于站点详情页无地区/年份/语言字段，无法提供这些筛选，故只保留"类型"一项，避免误导用户。
const TYPE_FILTER = classList.map(c => ({ "n": c.type_name, "v": c.type_id }));

function buildFilters(tid) {
    return [
        { "key": "cate", "name": "类型", "value": TYPE_FILTER }
    ];
}

const myFilters = {};
classList.forEach(item => {
    myFilters[item.type_id] = buildFilters(item.type_id);
});

// ===================== HTTP =====================
async function httpGet(url) {
    const headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "identity",
        "Referer": appConfig.siteUrl + "/"
    };
    for (let attempt = 0; attempt < 3; attempt++) {
        try {
            const resp = await req(url, { method: "GET", headers: headers, timeout: 15000 });
            let content = resp.content || resp.body || "";
            if (content && content.length > 200) return content;
            if (attempt < 2) await new Promise(r => setTimeout(r, 500));
        } catch (e) {
            if (attempt < 2) await new Promise(r => setTimeout(r, 500));
        }
    }
    try {
        const resp = await req(url, { method: "GET", headers: headers, timeout: 15000 });
        return resp.content || resp.body || "";
    } catch (e) {
        return "";
    }
}

// ===================== 列表页解析 =====================
// 卡片结构（实测）：<a class="vcard" href="/voddetail/{id}.html">
//   海报：img.lazyload[data-original]
//   标题：.vcard 下第一个 <p class="...truncate">
//   备注：海报右下角 div（如 HD国语）/ 左上角 span（评分）
function parseListHtml(html) {
    const $ = cheerio.load(html);
    let list = [];
    let seen = {};

    $('a.vcard').each(function () {
        let a = $(this);
        let href = a.attr('href') || '';
        let m = href.match(/\/voddetail\/(\d+)\.html/);
        if (!m) return;
        let vod_id = m[1];
        if (seen[vod_id]) return;
        seen[vod_id] = true;

        let img = a.find('img').first();
        let vod_pic = img.attr('data-original') || img.attr('data-src') ||
            img.attr('data-lazy') || img.attr('src') || '';
        if (vod_pic && vod_pic.indexOf('http') !== 0) {
            // 跳过模板占位图（load.svg 等）
            if (/load\.svg|loading/i.test(vod_pic)) vod_pic = '';
            else vod_pic = appConfig.siteUrl + '/' + vod_pic.replace(/^\.?\//, '');
        }

        // 标题：第一个带 truncate 的 <p>（紧跟海报块之后）
        let vod_name = '';
        a.find('p').each(function () {
            let cls = $(this).attr('class') || '';
            let txt = $(this).text().trim();
            if (!txt) return;
            // 标题段（含 font-bold），演员段是 text-gray-400，排除
            if (cls.indexOf('font-bold') !== -1 || (cls.indexOf('truncate') !== -1 && cls.indexOf('gray') === -1)) {
                vod_name = txt;
                return false;
            }
        });
        if (!vod_name) vod_name = img.attr('alt') || '';
        vod_name = vod_name.replace(/^《|》$/g, '').trim();
        if (!vod_name) return;

        // 备注：海报右下角文字（HD国语 / 正片 / 更新至N集）
        let vod_remarks = '';
        a.find('div').each(function () {
            if (vod_remarks) return;
            let d = $(this);
            let cls = d.attr('class') || '';
            let txt = d.text().trim();
            if (!txt) return;
            // 右下角备注块 class 含 bottom/right，左上角评分块含 top/left（评分当 remarks 不合适）
            if (/bottom/.test(cls) && /right/.test(cls) && txt.length < 12) {
                vod_remarks = txt;
            }
        });
        if (!vod_remarks) {
            // 兜底：从图片同层 div 找短文本
            let rm = a.text().match(/(HD国语|HD粤语|HD|BD|DVD|抢先版|正片|预告|TS|TC|蓝光|超清|高清|4K|更新至\d+|\d+集全)/);
            if (rm) vod_remarks = rm[1];
        }

        list.push({ vod_id, vod_name, vod_pic, vod_remarks });
    });

    // 分页：实测 <a class="page-btn" href="/vodtype/{tid}-{page}.html">
    let maxPage = 0;
    let hasNext = false;
    $('a.page-btn, .pagination a, a[href*="/vodtype/"]').each(function () {
        let href = $(this).attr('href') || '';
        let text = $(this).text().trim();
        if (/下一页|»|next/i.test(text)) hasNext = true;
        let mm = href.match(/\/vodtype\/\d+-(\d+)\.html/);
        if (mm) {
            let p = parseInt(mm[1]);
            if (p > maxPage && p < 9999) maxPage = p;
        }
    });
    // 当前页 class 含 active
    $('a.page-btn.active').each(function () {
        let p = parseInt($(this).text().trim());
        if (p > maxPage) maxPage = p;
    });

    let pagecount;
    if (list.length === 0) pagecount = 0;
    else if (hasNext) pagecount = maxPage + 1;
    else pagecount = Math.max(maxPage, 1);
    return { list, pagecount };
}

async function home(filter) {
    let list = [];
    try {
        const html = await httpGet(appConfig.siteUrl + '/');
        list = parseListHtml(html).list.slice(0, 30);
    } catch (e) {
        console.error("首页获取失败:", e.message);
    }
    return JSON.stringify({
        class: classList,
        filters: myFilters,
        list: list
    });
}

// ===================== 分类列表（带类型筛选 + 分页）=====================
async function category(tid, pg, filter, extend) {
    pg = pg || 1;
    extend = extend || {};
    try {
        // "类型"筛选：若用户选了某个子分类 type_id，则切换到该 type_id 拉取；
        // 否则用当前 tid。站点筛选页已关闭，类型切换是唯一可用筛选。
        let useTid = (extend.cate && extend.cate !== tid) ? extend.cate : tid;
        let url;
        if (parseInt(pg) > 1) {
            url = appConfig.siteUrl + '/vodtype/' + useTid + '-' + pg + '.html';
        } else {
            url = appConfig.siteUrl + '/vodtype/' + useTid + '.html';
        }
        const html = await httpGet(url);
        const result = parseListHtml(html);
        return JSON.stringify({ list: result.list, pagecount: result.pagecount });
    } catch (e) {
        console.error("分类列表获取失败:", e.message);
        return JSON.stringify({ list: [], pagecount: 0 });
    }
}

// ===================== 详情页解析 =====================
async function detail(id) {
    try {
        let detailUrl = appConfig.siteUrl + '/voddetail/' + String(id).replace(/^\/+/, '') + '.html';
        const html = await httpGet(detailUrl);
        const $ = cheerio.load(html);

        // 标题：取 <title> 前半段《片名》或 h1
        let vod_name = '';
        let h1 = $('h1').first().text().trim();
        if (h1) vod_name = h1;
        if (!vod_name) {
            let tm = html.match(/<title>([^<]+)/);
            if (tm) vod_name = tm[1].replace(/[-_–—《》].*$/, '').replace(/^《|》$/g, '').trim();
        }
        vod_name = vod_name.replace(/^《|》$/g, '').trim();

        // 海报：详情页主图
        let vod_pic = '';
        let img = $('.detail-pic img, .voddetail img, img.lazyload').first();
        if (img.length) {
            vod_pic = img.attr('data-original') || img.attr('data-src') ||
                img.attr('data-lazy') || img.attr('src') || '';
            if (vod_pic && vod_pic.indexOf('http') !== 0) {
                if (/load\.svg|loading/i.test(vod_pic)) vod_pic = '';
                else vod_pic = appConfig.siteUrl + '/' + vod_pic.replace(/^\.?\//, '');
            }
        }

        // 元数据（实测模板信息块：<span class="text-gray-400">标签：</span>值）
        let vod_director = '', vod_actor = '', vod_remarks = '', vod_content = '', vod_class = '';
        $('span.text-gray-400, span.text-gray-500').each(function () {
            let label = $(this).text().replace(/[：:]/g, '').trim();
            // 值是该 span 之后的同层文本（直到下一个 span 或标签结束）
            let parent = $(this).parent();
            let raw = parent.text().trim();
            // 去掉所有标签文本后剩下的即当前字段值
            let value = raw.replace($(this).text(), '').replace(/^[·\s]+/, '').split('·')[0].trim();
            if (/导演/.test(label)) vod_director = value;
            else if (/主演/.test(label)) vod_actor = value;
            else if (/更新|状态|备注/.test(label)) vod_remarks = value;
        });

        // 简介：meta description（详情页无独立简介块）
        let meta = html.match(/<meta\s+name="description"\s+content="([^"]+)"/);
        if (meta) vod_content = meta[1].replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ')
            .replace(/^[^：]+：/, '').trim().substring(0, 500);

        // 类型：从 keywords 提取（如"...电影爱情片..."→爱情片）
        let mk = html.match(/<meta\s+name="keywords"\s+content="([^"]+)"/);
        if (mk) {
            let km = mk[1].match(/电影([^\s,，]+)/) || mk[1].match(/电视剧([^\s,，]+)/);
            if (km) vod_class = km[1].replace(/片$/, '');
        }

        // ===== 播放线路 + 选集 =====
        // 线路名：<button class="tab-btn" data-sid="{sid}">线路名</button>
        // 选集：<a class="ep-item" data-nid="{nid}" href="/vodplay/{vodId}-{sid}-{nid}.html">集名</a>
        // 注意：详情页顶部有"立即播放"大按钮（class 为 flex-1，非 ep-item，无 data-nid），
        //       不能用 a[href*="/vodplay/"] 这种宽选择器，否则会把"立即播放"误收为剧集，
        //       导致线路分组错乱、选集里混入"立即播放"。只选 a.ep-item 并要求有 data-nid。
        let lineNames = {};        // sid -> name
        $('button.tab-btn').each(function () {
            let sid = $(this).attr('data-sid');
            let name = $(this).text().trim();
            if (sid && name && !lineNames[sid]) lineNames[sid] = name;
        });

        let lineMap = {};          // sid -> [{epName, href, nid}]
        let lineOrder = [];
        $('a.ep-item').each(function () {
            let a = $(this);
            // 必须有 data-nid 才是真正的选集（排除"立即播放"按钮）
            let nid = a.attr('data-nid');
            if (!nid) return;
            let href = a.attr('href') || '';
            let mm = href.match(/\/vodplay\/\d+-(\d+)-(\d+)\.html/);
            if (!mm) return;
            let sid = mm[1];
            let epName = a.text().trim();
            // 过滤掉"立即播放"等非集名文本
            if (!epName || /立即播放|播放/.test(epName)) return;
            if (!lineMap[sid]) { lineMap[sid] = []; lineOrder.push(sid); }
            lineMap[sid].push({ epName: epName, href: href, nid: parseInt(nid) });
        });

        let lines = [];
        let playlists = [];
        lineOrder.forEach((sid, idx) => {
            let name = lineNames[sid] || ('线路' + (idx + 1));
            let eps = lineMap[sid];
            if (!eps || eps.length === 0) return;
            // 按 nid 升序排序
            eps.sort((a, b) => a.nid - b.nid);
            // 去重（同一 nid 只保留一条）
            let seenNid = {};
            let epList = [];
            eps.forEach(e => {
                if (seenNid[e.nid]) return;
                seenNid[e.nid] = true;
                epList.push(e.epName + '$' + e.href);
            });
            if (epList.length === 0) return;
            lines.push(name);
            playlists.push(epList);
        });

        if (lines.length === 0) {
            lines.push('默认线路');
            playlists.push(['暂无播放地址$' + id]);
        }

        const vod_play_from = lines.join('$$$');
        const vod_play_url = playlists.map(eps => eps.join('#')).join('$$$');

        return JSON.stringify({
            list: [{
                vod_id: String(id),
                vod_name,
                vod_pic,
                vod_actor,
                vod_director,
                vod_remarks,
                vod_content,
                vod_class,
                vod_play_from,
                vod_play_url
            }]
        });
    } catch (error) {
        console.error("解析详情异常:", error);
        return JSON.stringify({ list: [] });
    }
}

// ===================== 播放解析 =====================
// macCMS 标准播放页含 player_aaaa 变量；encrypt:0 明文 url 直接是 m3u8。
// 本站实测 encrypt=0，url 为直链 m3u8（如 https://vip.dytt-see.com/.../index.m3u8）。
function decodePlayerUrl(cfg) {
    if (!cfg) return '';
    let u = cfg.url || '';
    let enc = parseInt(cfg.encrypt || 0);
    try {
        if (enc === 0) return u;
        if (enc === 1) return decodeURIComponent(u);
        if (enc === 2) { let t = u; try { t = unescape(t); } catch (e) {} try { t = decodeURIComponent(t); } catch (e) {} return t; }
        return u;
    } catch (e) {
        return u;
    }
}

async function play(flag, id, flags) {
    try {
        let playUrl = String(id || '');

        // 直链 m3u8/mp4 直接放行
        if (/\.m3u8|\.mp4/i.test(playUrl) && playUrl.indexOf('/vodplay/') === -1) {
            return JSON.stringify({
                parse: 0,
                Header: { "User-Agent": UA, "Referer": appConfig.siteUrl + "/" },
                url: playUrl
            });
        }

        // 播放页 URL：/vodplay/{vodId}-{sid}-{nid}.html
        let playPage = playUrl;
        if (playPage.indexOf('http') !== 0) {
            playPage = appConfig.siteUrl + '/' + playPage.replace(/^\/+/, '');
        }

        const html = await httpGet(playPage);

        // 1. 解析 player_aaaa（实测本站 encrypt=0，url 为直链 m3u8）
        let playLink = '';
        let m = html.match(/player_aaaa\s*=\s*(\{[\s\S]*?\})\s*[;<\n]/);
        if (m) {
            try {
                let cfg = JSON.parse(m[1]);
                playLink = decodePlayerUrl(cfg);
            } catch (e) {}
        }

        // 2. 兜底：正则匹配页面 m3u8/mp4 直链
        if (!playLink) {
            let mm = html.match(/(https?:\/\/[^\s"'<>]+\.m3u8[^\s"'<>]*)/);
            if (mm) playLink = mm[1];
        }
        if (!playLink) {
            let mm2 = html.match(/(https?:\/\/[^\s"'<>]+\.mp4[^\s"'<>]*)/);
            if (mm2) playLink = mm2[1];
        }

        // 3. 兜底：从 "url":"xxx" 提取并解码
        if (!playLink) {
            let um = html.match(/["']url["']\s*:\s*["']([^"']+)["']/);
            if (um) {
                let u = um[1].replace(/\\\//g, '/');
                try { playLink = decodeURIComponent(u); } catch (e) { playLink = u; }
            }
        }

        if (playLink && /^https?:\/\//.test(playLink)) {
            return JSON.stringify({
                parse: 0,
                Header: { "User-Agent": UA, "Referer": appConfig.siteUrl + "/" },
                url: playLink
            });
        }

        // 4. 最终兜底：交给播放器嗅探播放页
        return JSON.stringify({
            parse: 1,
            Header: { "User-Agent": UA, "Referer": appConfig.siteUrl + "/" },
            url: playPage
        });
    } catch (e) {
        console.error("播放失败:", e);
        return JSON.stringify({ parse: 0, url: "" });
    }
}

// ===================== 搜索 =====================
async function search(wd, quick, page) {
    page = page || 1;
    try {
        let kw = String(wd || '').trim();
        if (!kw) return JSON.stringify({ list: [], pagecount: 0 });

        // macCMS 搜索 URL：/vodsearch/{wd}-------------.html（13 段）
        // 翻页用 page 段：/vodsearch/{wd}-------------{page}-.html（实测第 13 段为页码）
        let url;
        if (parseInt(page) > 1) {
            url = appConfig.siteUrl + '/vodsearch/' + encodeURIComponent(kw) +
                '-------------' + page + '-.html';
        } else {
            url = appConfig.siteUrl + '/vodsearch/' + encodeURIComponent(kw) +
                '-------------.html';
        }
        const html = await httpGet(url);

        // 搜索结果页卡片结构与列表页一致（a.vcard）
        const result = parseListHtml(html);

        // 搜索结果分页：a[href*="/vodsearch/"] 含页码
        const $ = cheerio.load(html);
        let maxPage = 0;
        let hasNext = false;
        $('a').each(function () {
            let href = $(this).attr('href') || '';
            let text = $(this).text().trim();
            if (/下一页|»|next/i.test(text)) hasNext = true;
            let mm = href.match(/\/vodsearch\/[^?]*-+(\d+)-?\.html$/);
            if (mm) {
                let p = parseInt(mm[1]);
                if (p > maxPage && p < 9999) maxPage = p;
            }
        });

        let pagecount = result.pagecount;
        if (hasNext) pagecount = Math.max(pagecount, maxPage + 1);
        return JSON.stringify({ list: result.list, pagecount: pagecount });
    } catch (e) {
        console.error("搜索失败:", e.message);
        return JSON.stringify({ list: [], pagecount: 0 });
    }
}

export default {
    init,
    home,
    category,
    detail,
    search,
    play
};
