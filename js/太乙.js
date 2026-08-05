import cheerio from 'assets://js/lib/cheerio.min.js';

// ===================== 站点配置 =====================
const appConfig = {
    siteName: "太乙电影",
    siteUrl: "https://ww98.taiee.xyz"
};

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

// 本站为 macCMS（苹果CMS）站点，提供标准 JSON 接口：
//   /api.php/provide/vod/?ac=detail&pg={页码}            全部影片列表（每页20条，共18页359条）
//   /api.php/provide/vod/?ac=detail&ids={id}             单部影片详情
// 接口的 type/class/area/year/lang 等服务端筛选在本站失效（返回全量数据），
// 故采用"拉取全量 + 客户端筛选"策略：按 type_id 与各字段在本地过滤后再分页返回。

async function init(ext) {
    console.log("初始化爬虫:", appConfig.siteName);
}

// ===================== 分类列表 =====================
// 实测 type_id：电影(20) 剧集(21) 综艺(22) 动漫(23)
const classList = [
    { type_id: "20", type_name: "电影" },
    { type_id: "21", type_name: "剧集" },
    { type_id: "22", type_name: "综艺" },
    { type_id: "23", type_name: "动漫" }
];

// ===================== 筛选配置 =====================
// 实测各字段取值（来自全量 ac=detail 的 vod_class / vod_area / vod_year / vod_lang）。
// vod_class 字段在本站混杂了类型/年份/地区/出品方，故"类型"筛选取常见类型关键词。

const TYPE_FILTER = [
    ["全部", "all"],
    ["剧情", "剧情"], ["喜剧", "喜剧"], ["动作", "动作"], ["爱情", "爱情"], ["科幻", "科幻"],
    ["悬疑", "悬疑"], ["惊悚", "惊悚"], ["恐怖", "恐怖"], ["犯罪", "犯罪"], ["冒险", "冒险"],
    ["奇幻", "奇幻"], ["武侠", "武侠"], ["古装", "古装"], ["战争", "战争"], ["历史", "历史"],
    ["动画", "动画"], ["动漫", "动漫"], ["纪录", "纪录"], ["传记", "传记"], ["家庭", "家庭"],
    ["热血", "热血"], ["搞笑", "搞笑"], ["校园", "校园"], ["玄幻", "玄幻"], ["仙侠", "仙侠"],
    ["都市", "都市"], ["年代", "年代"], ["军旅", "军旅"], ["警匪", "警匪"], ["谍战", "谍战"],
    ["宫斗", "宫斗"], ["穿越", "穿越"], ["运动", "运动"], ["音乐", "音乐"], ["歌舞", "歌舞"],
    ["真人秀", "真人秀"], ["脱口秀", "脱口秀"], ["选秀", "选秀"], ["访谈", "访谈"]
];

const AREA_FILTER = [
    ["全部", "all"], ["大陆", "大陆"], ["内地", "内地"], ["中国大陆", "中国大陆"],
    ["中国香港", "中国香港"], ["中国台湾", "中国台湾"], ["日本", "日本"], ["韩国", "韩国"],
    ["美国", "美国"], ["英国", "英国"], ["法国", "法国"], ["意大利", "意大利"],
    ["加拿大", "加拿大"], ["巴西", "巴西"], ["丹麦", "丹麦"], ["其他", "其他"]
];

const YEAR_FILTER = [
    ["全部", "all"], ["2026", "2026"], ["2025", "2025"], ["2024", "2024"], ["2023", "2023"],
    ["2022", "2022"], ["2021", "2021"], ["2020", "2020"], ["2019", "2019"], ["2018", "2018"],
    ["2017", "2017"], ["2016", "2016"], ["2015", "2015"], ["2010-2014", "2010-2014"],
    ["2000-2009", "2000-2009"], ["更早", "更早"]
];

const LANG_FILTER = [
    ["全部", "all"], ["国语", "国语"], ["普通话", "普通话"], ["汉语普通话", "汉语普通话"],
    ["粤语", "粤语"], ["英语", "英语"], ["日语", "日语"], ["韩语", "韩语"], ["其他", "其他"]
];

const SORT_FILTER = [
    ["最新", "time"], ["最热", "hits"], ["评分", "score"]
];

function toFilterObj(arr) {
    return arr.map(g => ({ "n": g[0], "v": g[1] }));
}

function buildFilters(tid) {
    return [
        { "key": "cate", "name": "类型", "value": toFilterObj(TYPE_FILTER) },
        { "key": "area", "name": "地区", "value": toFilterObj(AREA_FILTER) },
        { "key": "year", "name": "年份", "value": toFilterObj(YEAR_FILTER) },
        { "key": "lang", "name": "语言", "value": toFilterObj(LANG_FILTER) },
        { "key": "by", "name": "排序", "value": toFilterObj(SORT_FILTER) }
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
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": appConfig.siteUrl + "/"
    };
    for (let attempt = 0; attempt < 3; attempt++) {
        try {
            const resp = await req(url, { method: "GET", headers: headers, timeout: 15000 });
            let content = resp.content || resp.body || "";
            if (content && content.length > 20) return content;
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

async function fetchApiJson(params) {
    let url = appConfig.siteUrl + "/api.php/provide/vod/?ac=detail";
    for (let k in params) {
        if (params[k] !== undefined && params[k] !== null && params[k] !== "") {
            url += "&" + k + "=" + encodeURIComponent(params[k]);
        }
    }
    let body = await httpGet(url);
    try {
        return JSON.parse(body);
    } catch (e) {
        return { code: 0, list: [], pagecount: 0, total: 0 };
    }
}

// ===================== 筛选辅助 =====================
function matchCate(vodClass, cate) {
    if (!cate || cate === "all") return true;
    if (!vodClass) return false;
    let parts = vodClass.split(",").map(s => s.trim());
    return parts.indexOf(cate) !== -1;
}

function matchArea(vodArea, area) {
    if (!area || area === "all") return true;
    if (!vodArea) return false;
    if (area === "其他") {
        let known = ["大陆", "内地", "中国大陆", "中国香港", "中国台湾", "中国",
            "日本", "韩国", "美国", "英国", "法国", "意大利", "加拿大", "巴西", "丹麦"];
        let first = vodArea.split(",")[0].trim();
        return known.indexOf(first) === -1 && known.indexOf(vodArea) === -1;
    }
    return vodArea.indexOf(area) !== -1;
}

function matchYear(vodYear, year) {
    if (!year || year === "all") return true;
    if (!vodYear) return false;
    let y = parseInt(vodYear) || 0;
    if (!y) return false;
    if (year === "更早") return y < 2000;
    if (year === "2010-2014") return y >= 2010 && y <= 2014;
    if (year === "2000-2009") return y >= 2000 && y <= 2009;
    return vodYear === year;
}

function matchLang(vodLang, lang) {
    if (!lang || lang === "all") return true;
    if (!vodLang) return false;
    if (lang === "其他") {
        let known = ["国语", "普通话", "汉语普通话", "粤语", "英语", "日语", "韩语"];
        return known.indexOf(vodLang) === -1;
    }
    return vodLang.indexOf(lang) !== -1;
}

function sortBy(items, by) {
    if (by === "hits") {
        items.sort((a, b) => (parseInt(b.vod_hits) || 0) - (parseInt(a.vod_hits) || 0));
    } else if (by === "score") {
        items.sort((a, b) => (parseFloat(b.vod_score) || 0) - (parseFloat(a.vod_score) || 0));
    } else {
        items.sort((a, b) => (b.vod_time || "").localeCompare(a.vod_time || ""));
    }
    return items;
}

// 全量列表共享缓存（所有分类共用一份），避免每个分类都重复拉 18 页。
let allCache = null; // { items: [...], ts: number }
const CACHE_TTL = 10 * 60 * 1000; // 10 分钟

// 拉取全站全量影片（接口 type 参数失效，只能拉全局再客户端过滤）
async function fetchAll() {
    let now = Date.now();
    if (allCache && (now - allCache.ts) < CACHE_TTL) {
        return allCache.items;
    }
    let all = [];
    let pg = 1;
    let pagecount = 1;
    while (pg <= pagecount && pg <= 50) {
        let data = await fetchApiJson({ pg: pg });
        if (!data || !data.list || data.list.length === 0) break;
        pagecount = parseInt(data.pagecount) || pagecount;
        for (let v of data.list) all.push(v);
        pg++;
        if (all.length > 2000) break; // 安全上限
    }
    allCache = { items: all, ts: now };
    return all;
}

// 按分类过滤（客户端按 type_id 过滤，因接口 type 参数失效）
async function fetchAllByType(tid) {
    let all = await fetchAll();
    return all.filter(v => String(v.type_id) === String(tid));
}

// 统计每个分类的影片数量，用于在分类名后显示数量（如"电影(125)"）
async function buildClassListWithCount() {
    let all = await fetchAll();
    let counts = {};
    for (let v of all) {
        let t = String(v.type_id);
        counts[t] = (counts[t] || 0) + 1;
    }
    return classList.map(c => ({
        type_id: c.type_id,
        type_name: c.type_name + "(" + (counts[c.type_id] || 0) + ")"
    }));
}

// ===================== 列表项映射 =====================
function toListItem(v) {
    let item = {
        vod_id: String(v.vod_id),
        vod_name: v.vod_name || "",
        vod_pic: v.vod_pic || "",
        vod_remarks: v.vod_remarks || ""
    };
    if (v.vod_year) item.vod_year = String(v.vod_year);
    if (v.vod_area) item.vod_area = v.vod_area;
    if (v.vod_class) item.vod_class = v.vod_class;
    return item;
}

// ===================== 首页 =====================
async function home(filter) {
    let list = [];
    let classWithCount = classList;
    try {
        let all = await fetchAll();
        // 首页推荐：取最新更新的 30 条（按 vod_time 降序）
        let sorted = all.slice().sort((a, b) =>
            (b.vod_time || "").localeCompare(a.vod_time || ""));
        list = sorted.slice(0, 30).map(toListItem);
        // 分类名带数量
        classWithCount = await buildClassListWithCount();
    } catch (e) {
        console.error("首页获取失败:", e.message);
    }
    return JSON.stringify({
        class: classWithCount,
        filters: myFilters,
        list: list
    });
}

// ===================== 分类列表（带筛选 + 分页）=====================
async function category(tid, pg, filter, extend) {
    pg = pg || 1;
    extend = extend || {};
    const PAGE_SIZE = 20;
    try {
        let all = await fetchAllByType(tid);

        // 客户端筛选
        let filtered = all.filter(v => {
            return matchCate(v.vod_class, extend.cate) &&
                matchArea(v.vod_area, extend.area) &&
                matchYear(v.vod_year, extend.year) &&
                matchLang(v.vod_lang, extend.lang);
        });

        // 排序
        sortBy(filtered, extend.by || "time");

        // 分页
        let total = filtered.length;
        let pagecount = Math.max(1, Math.ceil(total / PAGE_SIZE));
        let start = (pg - 1) * PAGE_SIZE;
        let pageItems = filtered.slice(start, start + PAGE_SIZE).map(toListItem);

        return JSON.stringify({ list: pageItems, pagecount: pagecount });
    } catch (e) {
        console.error("分类列表获取失败:", e.message);
        return JSON.stringify({ list: [], pagecount: 0 });
    }
}

// ===================== 详情页 =====================
async function detail(id) {
    try {
        let data = await fetchApiJson({ ids: id });
        if (!data || !data.list || data.list.length === 0) {
            return JSON.stringify({ list: [] });
        }
        let v = data.list[0];

        let vod_content = (v.vod_content || v.vod_blurb || "").replace(/<[^>]+>/g, "").trim();
        if (vod_content.length > 500) vod_content = vod_content.substring(0, 500);

        // ===== 播放线路 + 选集 =====
        // macCMS 标准：vod_play_from 用 $$$ 分隔线路，vod_play_url 用 $$$ 分隔线路、# 分隔集数、$ 分隔集名与URL
        // 本站播放地址均为外链（v.qq.com/youku/iqiyi/mgtv），直接交给播放器嗅探。
        let lines = [];
        let playlists = [];
        let pf = (v.vod_play_from || "").split("$$$");
        let pu = (v.vod_play_url || "").split("$$$");
        for (let i = 0; i < pf.length; i++) {
            let lineName = (pf[i] || "").trim();
            let eps = (pu[i] || "").split("#").filter(e => e.indexOf("$") !== -1);
            if (!lineName || eps.length === 0) continue;
            let epList = eps.map(e => {
                let idx = e.indexOf("$");
                return e.substring(0, idx) + "$" + e.substring(idx + 1);
            });
            lines.push(lineName);
            playlists.push(epList);
        }

        if (lines.length === 0) {
            lines.push("默认线路");
            playlists.push(["暂无播放地址$" + id]);
        }

        const vod_play_from = lines.join("$$$");
        const vod_play_url = playlists.map(eps => eps.join("#")).join("$$$");

        return JSON.stringify({
            list: [{
                vod_id: String(v.vod_id),
                vod_name: v.vod_name || "",
                vod_pic: v.vod_pic || "",
                vod_actor: v.vod_actor || "",
                vod_director: v.vod_director || "",
                vod_remarks: v.vod_remarks || "",
                vod_year: v.vod_year ? String(v.vod_year) : "",
                vod_area: v.vod_area || "",
                vod_lang: v.vod_lang || "",
                vod_content: vod_content,
                vod_class: v.vod_class || "",
                vod_play_from,
                vod_play_url
            }]
        });
    } catch (error) {
        console.error("解析详情异常:", error);
        return JSON.stringify({ list: [] });
    }
}

// ===================== 播放 =====================
// 本站播放地址均为外部视频站直链（腾讯/优酷/爱奇艺/芒果），交给播放器嗅探播放页。
async function play(flag, id, flags) {
    try {
        let playUrl = String(id || "");
        return JSON.stringify({
            parse: 1,
            Header: { "User-Agent": UA, "Referer": appConfig.siteUrl + "/" },
            url: playUrl
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
        let kw = String(wd || "").trim();
        if (!kw) return JSON.stringify({ list: [], pagecount: 0 });

        // macCMS provide 接口 wd 参数：实测本站 wd 服务端筛选失效，故客户端模糊匹配。
        // 复用全量共享缓存。
        let all = await fetchAll();

        let matched = all.filter(v => {
            let name = v.vod_name || "";
            let tag = v.vod_tag || "";
            let actor = v.vod_actor || "";
            return name.indexOf(kw) !== -1 || tag.indexOf(kw) !== -1 || actor.indexOf(kw) !== -1;
        });

        const PAGE_SIZE = 20;
        let total = matched.length;
        let pcount = Math.max(1, Math.ceil(total / PAGE_SIZE));
        let start = (page - 1) * PAGE_SIZE;
        let pageItems = matched.slice(start, start + PAGE_SIZE).map(toListItem);

        return JSON.stringify({ list: pageItems, pagecount: pcount });
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
