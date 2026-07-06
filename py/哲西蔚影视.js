import cheerio from 'assets://js/lib/cheerio.min.js';

const appConfig = {
    siteName: "4k影视资源网",
    siteUrl: "https://www.4kyszxw.com"
}
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36";
const Headers = {
    "User-Agent": UA,
    "Referer": appConfig.siteUrl + "/",
}

async function init(ext) {
    console.log("初始化爬虫:", appConfig.siteName);
}

function getYearFilter() {
    let years = [{ "n": "全部", "v": "all" }];
    const currentYear = new Date().getFullYear();
    for (let y = currentYear; y >= currentYear - 16; y--) {
        years.push({ "n": String(y), "v": String(y) });
    }
    return { "key": "year", "name": "年份", "value": years };
}

function getSortFilter() {
    return {
        "key": "sort", "name": "排序", "value": [
            { "n": "最近更新", "v": "all" },
            { "n": "最多播放", "v": "hits" },
            { "n": "最好评", "v": "score" }
        ]
    }
}

const areaFilter = {
    "key": "area", "name": "地区", "value": [
        { "n": "全部", "v": "all" },
        { "n": "大陆", "v": "大陆" }, { "n": "香港", "v": "香港" }, { "n": "台湾", "v": "台湾" },
        { "n": "美国", "v": "美国" }, { "n": "法国", "v": "法国" }, { "n": "英国", "v": "英国" },
        { "n": "日本", "v": "日本" }, { "n": "韩国", "v": "韩国" }, { "n": "德国", "v": "德国" },
        { "n": "泰国", "v": "泰国" }, { "n": "印度", "v": "印度" }, { "n": "意大利", "v": "意大利" },
        { "n": "西班牙", "v": "西班牙" }, { "n": "加拿大", "v": "加拿大" }, { "n": "其他", "v": "其他" }
    ]
};

const langFilter = {
    "key": "lang", "name": "语言", "value": [
        { "n": "全部", "v": "all" },
        { "n": "国语", "v": "国语" }, { "n": "英语", "v": "英语" }, { "n": "粤语", "v": "粤语" },
        { "n": "闽南语", "v": "闽南语" }, { "n": "韩语", "v": "韩语" }, { "n": "日语", "v": "日语" },
        { "n": "法语", "v": "法语" }, { "n": "德语", "v": "德语" }, { "n": "其它", "v": "其它" }
    ]
};

const movieClassFilter = {
    "key": "class", "name": "剧情", "value": [
        { "n": "全部", "v": "all" },
        { "n": "喜剧", "v": "喜剧" }, { "n": "爱情", "v": "爱情" }, { "n": "恐怖", "v": "恐怖" },
        { "n": "动作", "v": "动作" }, { "n": "科幻", "v": "科幻" }, { "n": "剧情", "v": "剧情" },
        { "n": "战争", "v": "战争" }, { "n": "警匪", "v": "警匪" }, { "n": "犯罪", "v": "犯罪" },
        { "n": "动画", "v": "动画" }, { "n": "奇幻", "v": "奇幻" }, { "n": "武侠", "v": "武侠" },
        { "n": "冒险", "v": "冒险" }, { "n": "枪战", "v": "枪战" }, { "n": "悬疑", "v": "悬疑" },
        { "n": "惊悚", "v": "惊悚" }, { "n": "经典", "v": "经典" }, { "n": "青春", "v": "青春" },
        { "n": "文艺", "v": "文艺" }, { "n": "微电影", "v": "微电影" }, { "n": "古装", "v": "古装" },
        { "n": "历史", "v": "历史" }, { "n": "运动", "v": "运动" }, { "n": "农村", "v": "农村" },
        { "n": "儿童", "v": "儿童" }, { "n": "网络电影", "v": "网络电影" }
    ]
};

const tvClassFilter = {
    "key": "class", "name": "剧情", "value": [
        { "n": "全部", "v": "all" },
        { "n": "古装", "v": "古装" }, { "n": "战争", "v": "战争" }, { "n": "青春偶像", "v": "青春偶像" },
        { "n": "喜剧", "v": "喜剧" }, { "n": "家庭", "v": "家庭" }, { "n": "犯罪", "v": "犯罪" },
        { "n": "动作", "v": "动作" }, { "n": "奇幻", "v": "奇幻" }, { "n": "剧情", "v": "剧情" },
        { "n": "历史", "v": "历史" }, { "n": "经典", "v": "经典" }, { "n": "乡村", "v": "乡村" },
        { "n": "情景", "v": "情景" }, { "n": "商战", "v": "商战" }, { "n": "网剧", "v": "网剧" },
        { "n": "其他", "v": "其他" }
    ]
};

const animeClassFilter = {
    "key": "class", "name": "剧情", "value": [
        { "n": "全部", "v": "all" },
        { "n": "情感", "v": "情感" }, { "n": "科幻", "v": "科幻" }, { "n": "热血", "v": "热血" },
        { "n": "推理", "v": "推理" }, { "n": "搞笑", "v": "搞笑" }, { "n": "冒险", "v": "冒险" },
        { "n": "萝莉", "v": "萝莉" }, { "n": "校园", "v": "校园" }, { "n": "动作", "v": "动作" },
        { "n": "机战", "v": "机战" }, { "n": "运动", "v": "运动" }, { "n": "战争", "v": "战争" },
        { "n": "少年", "v": "少年" }, { "n": "少女", "v": "少女" }, { "n": "社会", "v": "社会" },
        { "n": "原创", "v": "原创" }, { "n": "亲子", "v": "亲子" }, { "n": "益智", "v": "益智" },
        { "n": "励志", "v": "励志" }, { "n": "其他", "v": "其他" }
    ]
};

const showClassFilter = {
    "key": "class", "name": "剧情", "value": [
        { "n": "全部", "v": "all" },
        { "n": "选秀", "v": "选秀" }, { "n": "情感", "v": "情感" }, { "n": "访谈", "v": "访谈" },
        { "n": "播报", "v": "播报" }, { "n": "旅游", "v": "旅游" }, { "n": "音乐", "v": "音乐" },
        { "n": "美食", "v": "美食" }, { "n": "纪实", "v": "纪实" }, { "n": "曲艺", "v": "曲艺" },
        { "n": "生活", "v": "生活" }, { "n": "游戏互动", "v": "游戏互动" }
    ]
};

const commonFilters = [areaFilter, langFilter, getYearFilter(), getSortFilter()];

const myFilters = {
    "2": [
        {
            "key": "type", "name": "类型", "value": [
                { "n": "全部", "v": "2" },
                { "n": "国产剧", "v": "30" },
                { "n": "韩剧", "v": "15" },
                { "n": "美剧", "v": "14" },
                { "n": "港剧", "v": "13" },
                { "n": "日剧", "v": "16" },
                { "n": "台剧", "v": "27" },
                { "n": "泰剧", "v": "28" }
            ]
        },
        tvClassFilter,
        ...commonFilters
    ],
    "1": [
        {
            "key": "type", "name": "类型", "value": [
                { "n": "全部", "v": "1" },
                { "n": "动作片", "v": "6" },
                { "n": "爱情片", "v": "7" },
                { "n": "动画片", "v": "58" },
                { "n": "科幻片", "v": "8" },
                { "n": "恐怖片", "v": "9" },
                { "n": "喜剧片", "v": "11" },
                { "n": "剧情片", "v": "12" },
                { "n": "纪实片", "v": "24" }
            ]
        },
        movieClassFilter,
        ...commonFilters
    ],
    "5": [
        {
            "key": "type", "name": "类型", "value": [
                { "n": "全部", "v": "5" },
                { "n": "国产动漫", "v": "17" },
                { "n": "日本动漫", "v": "47" },
                { "n": "欧美动漫", "v": "49" },
                { "n": "香港动漫", "v": "18" },
                { "n": "韩国动漫", "v": "48" },
                { "n": "台湾动漫", "v": "46" }
            ]
        },
        animeClassFilter,
        ...commonFilters
    ],
    "29": [
        {
            "key": "type", "name": "类型", "value": [
                { "n": "全部", "v": "29" },
                { "n": "都市短剧", "v": "55" }
            ]
        },
        ...commonFilters
    ],
    "37": [
        {
            "key": "type", "name": "类型", "value": [
                { "n": "全部", "v": "37" },
                { "n": "大陆综艺", "v": "38" },
                { "n": "欧美综艺", "v": "43" },
                { "n": "香港综艺", "v": "39" },
                { "n": "日本综艺", "v": "41" }
            ]
        },
        showClassFilter,
        ...commonFilters
    ]
};

async function home(filter) {
    return JSON.stringify({
        class: [
            { type_id: "2", type_name: "电视剧" },
            { type_id: "1", type_name: "电影" },
            { type_id: "5", type_name: "动漫" },
            { type_id: "37", type_name: "综艺" },
            { type_id: "29", type_name: "短剧" }
        ],
        filters: myFilters
    });
}

async function category(tid, pg, filter, extend) {
    pg = pg || 1;
    extend = extend || {};
    let type = extend.type || tid;
    let classVal = extend.class || 'all';
    let areaVal = extend.area || 'all';
    let langVal = extend.lang || 'all';
    let yearVal = extend.year || 'all';
    let sortVal = extend.sort || 'all';

    let url;
    if (classVal === 'all' && areaVal === 'all' && langVal === 'all' && yearVal === 'all' && sortVal === 'all') {
        url = `${appConfig.siteUrl}/vs/${type}/${pg}.html`;
    } else {
        url = `${appConfig.siteUrl}/vs/${type}/${classVal}/${areaVal}/${langVal}/${yearVal}/${sortVal}/${pg}.html`;
    }

    try {
        const html = (await req(url, { headers: Headers })).content;
        const $ = cheerio.load(html);
        let list = [];

        $(".vod-list li.col-xs-4").each(function (index, el) {
            let vod_id = $(el).find(".pic a").attr("href");
            let vod_name = $(el).find(".pic a").attr("title");
            if (vod_name) vod_name = vod_name.trim();
            let vod_pic = $(el).find(".img-wrapper").attr("data-original");
            let vod_remarks = $(el).find(".item-status").text().trim();

            if (vod_id) {
                list.push({
                    vod_id,
                    vod_name,
                    vod_pic,
                    vod_remarks
                });
            }
        });

        let pagecount = 1;
        const numText = $(".ewave-page .num").text();
        if (numText) {
            const match = numText.match(/(\d+)\/(\d+)/);
            if (match) {
                pagecount = parseInt(match[2]);
            }
        }
        if (pagecount <= 1) {
            let maxPage = 1;
            $(".ewave-page a").each(function (i, el) {
                const href = $(el).attr("href");
                if (href) {
                    const pageMatch = href.match(/\/(\d+)\.html/);
                    if (pageMatch) {
                        const p = parseInt(pageMatch[1]);
                        if (p > maxPage) maxPage = p;
                    }
                }
            });
            pagecount = maxPage;
        }

        return JSON.stringify({
            list,
            pagecount
        });
    } catch (e) {
        console.error("分类列表获取失败:", e.message);
        return JSON.stringify({ list: [], pagecount: 0 });
    }
}

async function search(wd, quick, page) {
    page = page || 1;
    if (page >= 2) {
        return JSON.stringify({ list: [], pagecount: 1 });
    }

    try {
        const url = `${appConfig.siteUrl}/search.html?wd=${encodeURIComponent(wd)}&submit=`;
        const html = (await req(url, { headers: Headers })).content;
        const $ = cheerio.load(html);
        let list = [];

        $(".vod-list li.col-xs-4").each((i, el) => {
            const vod_id = $(el).find(".pic a").attr("href") || '';
            const vod_name = $(el).find(".pic a").attr("title") || '';
            const vod_pic = $(el).find(".img-wrapper").attr("data-original") || '';
            const vod_remarks = $(el).find(".item-status").text().trim();

            if (vod_id) {
                list.push({
                    vod_id,
                    vod_name: vod_name.trim(),
                    vod_pic,
                    vod_remarks
                });
            }
        });

        return JSON.stringify({
            list: list,
            pagecount: 1
        });
    } catch (e) {
        console.error("搜索失败:", e.message);
        return JSON.stringify({ list: [] });
    }
}

async function detail(id) {
    try {
        const url = appConfig.siteUrl + id;
        const html = (await req(url, { headers: Headers })).content;
        const $ = cheerio.load(html);

        const vod_name = $('.vod-info h2 a').text().trim();
        const imgSrc = $('.vod-info .pic img').attr("data-original") || '';
        const vod_pic = imgSrc ? (imgSrc.startsWith('http') ? imgSrc : appConfig.siteUrl + imgSrc) : '';

        let vod_actor = '';
        let vod_director = '';
        let vod_remarks = '';
        let vod_year = '';
        let vod_area = '';

        $('.vod-info .info p span').each((i, el) => {
            const text = $(el).text();
            if (text.includes('主演')) {
                vod_actor = $(el).find('a').map(function () {
                    return $(this).text().trim();
                }).get().join(',');
            } else if (text.includes('导演')) {
                vod_director = $(el).find('a').map(function () {
                    return $(this).text().trim();
                }).get().join(',');
            } else if (text.includes('状态')) {
                vod_remarks = text.replace('状态：', '').trim();
            } else if (text.includes('地区')) {
                vod_area = $(el).find('a').text().trim();
            } else if (text.includes('年份')) {
                vod_year = $(el).find('a').text().trim();
            }
        });

        const vod_content = $('.vod-info .info .text').text().trim();

        let rawLines = [];
        let rawPlaylists = [];

        $('.playlist-tab .ewave-tab').each((i, el) => {
            const lineName = $(el).text().trim();
            rawLines.push(lineName);
        });

        $('ul[id^="ewave-playlist-"]').each((lineIndex, poolEl) => {
            const episodes = [];
            $(poolEl).find('.ewave-playlist-item a').each((episodeIndex, epEl) => {
                const name = $(epEl).text().trim();
                const href = $(epEl).attr('href') || '';
                if (name && href) {
                    episodes.push(`${name}$${href}`);
                }
            });
            rawPlaylists.push(episodes);
        });

        let finalLines = [];
        let finalPlaylists = [];
        for (let i = 0; i < rawLines.length; i++) {
            if (rawPlaylists[i] && rawPlaylists[i].length > 0) {
                finalLines.push(rawLines[i]);
                finalPlaylists.push(rawPlaylists[i]);
            }
        }

        const { vod_play_from, vod_play_url } = buildVodPlayData(finalLines, finalPlaylists, false);

        const vod = {
            vod_id: id,
            vod_name,
            vod_pic,
            vod_actor,
            vod_director,
            vod_remarks,
            vod_year,
            vod_area,
            vod_content,
            vod_play_from,
            vod_play_url
        };

        return JSON.stringify({ list: [vod] });
    } catch (error) {
        console.error(`解析详情页异常 [ID: ${id}]:`, error);
        return JSON.stringify({ list: [] });
    }
}

function buildVodPlayData(lines, playlists, shouldReverse = false) {
    const processedPlaylists = playlists.map(eps => {
        if (shouldReverse) {
            eps.reverse();
        }
        return eps.join('#');
    });
    return {
        vod_play_from: lines.filter(Boolean).join('$$$'),
        vod_play_url: processedPlaylists.join('$$$')
    };
}

function isDirectUrl(url) {
    return url.startsWith('http') || url.endsWith(".m3u8") || url.endsWith(".mp4");
}

function getPlayUrl(html) {
    const match = html.match(/var\s+player_aaaa[\s\S]*?"url"\s*:\s*"([^"]+)"/);
    let url = match ? match[1] : '';
    url = url.replace(/\\/g, '');
    return url;
}

async function play(flag, id, flags) {
    try {
        const html = (await req(`${appConfig.siteUrl}${id}`, { headers: Headers })).content;
        const url = getPlayUrl(html);

        if (isDirectUrl(url)) {
            return JSON.stringify({
                parse: 0,
                Header: {
                    "User-Agent": UA
                },
                url,
            });
        }

        return JSON.stringify({
            parse: 1,
            Header: {
                "User-Agent": UA,
                "Referer": appConfig.siteUrl
            },
            url: url
        });
    } catch (e) {
        console.error("播放失败:", e);
        return JSON.stringify({ parse: 0, url: "" });
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
