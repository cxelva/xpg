let host = 'https://i3j4k5l6.mrfuli029.buzz';
let headers = {
  "User-Agent": "Mozilla/5.0 (Linux; Android 13; M2102J2SC Build/TKQ1.221114.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/143.0.7499.3 Mobile Safari/537.36"
};
async function init(cfg) {}

function getList(html) {
  let videos = [];
  let items = pdfa(html, ".vod");
  items.forEach(it => {
    let idMatch = it.match(/\/voddetail\/(\d+)\.html/);
    let nameMatch = it.match(/<div class="vod-txt">[\s\S]*?>(.*?)<\/a>/);
    let picMatch = it.match(/data-original="(.*?)"/) || it.match(/src="(.*?)"/);
    if (idMatch && nameMatch) {
      let pic = picMatch ? (picMatch[1] || picMatch[2]) : "";
      videos.push({
        vod_id: idMatch[1],
        vod_name: nameMatch[1].replace(/<.*?>/g, ""),
        vod_pic: pic.startsWith('/') ? host + pic : pic
      });
    }
  });
  return videos;
}
async function home(filter) {
  return JSON.stringify({
    "class": [{
        "type_id": "1",
        "type_name": "国产传媒"
      },
      {
        "type_id": "21",
        "type_name": "麻豆视频"
      },
      {
        "type_id": "27",
        "type_name": "精东影业"
      },
      {
        "type_id": "24",
        "type_name": "蜜桃传媒"
      },
      {
        "type_id": "28",
        "type_name": "乐播传媒"
      },
      {
        "type_id": "29",
        "type_name": "乌鸦传媒"
      },
      {
        "type_id": "23",
        "type_name": "天美传媒"
      },
      {
        "type_id": "30",
        "type_name": "兔子先生"
      },
      {
        "type_id": "26",
        "type_name": "星空传媒"
      },
      {
        "type_id": "2",
        "type_name": "国产剧情"
      },
      {
        "type_id": "35",
        "type_name": "开心鬼传媒"
      },
      {
        "type_id": "22",
        "type_name": "91制片厂"
      },
      {
        "type_id": "31",
        "type_name": "杏吧原创"
      },
      {
        "type_id": "34",
        "type_name": "大象传媒"
      },
      {
        "type_id": "25",
        "type_name": "皇家华人"
      },
      {
        "type_id": "33",
        "type_name": "mini传媒"
      },
      {
        "type_id": "37",
        "type_name": "糖心Vlog"
      },
      {
        "type_id": "39",
        "type_name": "性视界"
      },
      {
        "type_id": "234",
        "type_name": "热门爆料"
      },
      {
        "type_id": "235",
        "type_name": "国产大制作"
      },
      {
        "type_id": "236",
        "type_name": "乱伦毁三观"
      },
      {
        "type_id": "237",
        "type_name": "主播女网红"
      },
      {
        "type_id": "238",
        "type_name": "黑料网曝"
      },
      {
        "type_id": "239",
        "type_name": "高清无码"
      },
      {
        "type_id": "240",
        "type_name": "中文字幕"
      },
      {
        "type_id": "242",
        "type_name": "淫乱学生妹"
      },
      {
        "type_id": "245",
        "type_name": "偷拍自拍"
      },
      {
        "type_id": "246",
        "type_name": "经典 A V"
      },
      {
        "type_id": "251",
        "type_name": "国产视频"
      },
      {
        "type_id": "248",
        "type_name": "无码中文"
      },
      {
        "type_id": "247",
        "type_name": "有码中文"
      },
      {
        "type_id": "250",
        "type_name": "日本无码"
      },
      {
        "type_id": "249",
        "type_name": "日本有码"
      },
      {
        "type_id": "252",
        "type_name": "欧美高清"
      },
      {
        "type_id": "253",
        "type_name": "动漫剧情"
      },
      {
        "type_id": "199",
        "type_name": "成人头条"
      },
      {
        "type_id": "17",
        "type_name": "精品推荐"
      },
      {
        "type_id": "226",
        "type_name": "热门大瓜"
      },
      {
        "type_id": "227",
        "type_name": "麻豆探花"
      },
      {
        "type_id": "228",
        "type_name": "偷拍自拍"
      },
      {
        "type_id": "229",
        "type_name": "顶流网红"
      },
      {
        "type_id": "230",
        "type_name": "校园生活"
      },
      {
        "type_id": "231",
        "type_name": "户外野战"
      },
      {
        "type_id": "232",
        "type_name": "热门黑料"
      },
      {
        "type_id": "233",
        "type_name": "中文字幕"
      },
      {
        "type_id": "4",
        "type_name": "精品资源"
      },
      {
        "type_id": "53",
        "type_name": "网曝黑料"
      },
      {
        "type_id": "49",
        "type_name": "激情动漫"
      },
      {
        "type_id": "55",
        "type_name": "AV解说"
      },
      {
        "type_id": "48",
        "type_name": "国产主播"
      },
      {
        "type_id": "50",
        "type_name": "明星换脸"
      },
      {
        "type_id": "51",
        "type_name": "抖阴视频"
      },
      {
        "type_id": "54",
        "type_name": "伦理三级"
      },
      {
        "type_id": "52",
        "type_name": "女优明星"
      },
      {
        "type_id": "3",
        "type_name": "必射精选"
      },
      {
        "type_id": "46",
        "type_name": "强奸乱伦"
      },
      {
        "type_id": "47",
        "type_name": "制服诱惑"
      },
      {
        "type_id": "41",
        "type_name": "中文字幕"
      },
      {
        "type_id": "40",
        "type_name": "国产视频"
      },
      {
        "type_id": "45",
        "type_name": "欧美无码"
      },
      {
        "type_id": "42",
        "type_name": "国产传媒"
      },
      {
        "type_id": "43",
        "type_name": "日本有码"
      },
      {
        "type_id": "44",
        "type_name": "日本无码"
      },
      {
        "type_id": "5",
        "type_name": "特色仓库"
      },
      {
        "type_id": "56",
        "type_name": "SM调教"
      },
      {
        "type_id": "60",
        "type_name": "网红头条"
      },
      {
        "type_id": "58",
        "type_name": "极品媚黑"
      },
      {
        "type_id": "57",
        "type_name": "萝莉少女"
      },
      {
        "type_id": "63",
        "type_name": "VR视角"
      },
      {
        "type_id": "61",
        "type_name": "人妖系列"
      },
      {
        "type_id": "62",
        "type_name": "韩国主播"
      },
      {
        "type_id": "198",
        "type_name": "女同性恋"
      },
      {
        "type_id": "208",
        "type_name": "热播片库"
      },
      {
        "type_id": "209",
        "type_name": "黑料吃瓜"
      },
      {
        "type_id": "210",
        "type_name": "乱伦精品"
      },
      {
        "type_id": "211",
        "type_name": "欧美巨屌"
      },
      {
        "type_id": "212",
        "type_name": "约炮探花"
      },
      {
        "type_id": "213",
        "type_name": "网红主播"
      },
      {
        "type_id": "214",
        "type_name": "华语AV"
      },
      {
        "type_id": "215",
        "type_name": "极品学妹"
      }, {
        "type_id": "216",
        "type_name": "国产精品"
      }
    ]
  });
}
async function homeVod() {
  let resp = await req(host, {
    headers
  });
  return JSON.stringify({
    list: getList(resp.content)
  });
}
async function category(tid, pg, filter, extend) {
  let p = pg || 1;
  let targetId = (extend && extend.class) ? extend.class : tid;
  let url = host + "/vodtype/" + targetId + "-" + (parseInt(p) + ".html");
  let resp = await req(url, {
    headers
  });
  return JSON.stringify({
    list: getList(resp.content),
    page: parseInt(p)
  });
}
async function detail(id) {
  //二级链接拼接
  let url = host + '/voddetail/' + id + '.html';
  let resp = await req(url, {
    headers
  });
  let html = resp.content;
  //播放数组
  let playUrl = pdfa(html, ".main11").map(list => //播放列表(基本不用动)
    pdfa(list, "a").map(a => {
      //播放标题(基本不用动)
      let n = (a.match(/">(.*?)<\/a>/) || ["", "播放"])[1];
      //播放链接(基本不用动)
      let v = a.match(/href="(.*?)"/);
      return n + '$' + (v ? v[1] : "");
    }).join('#')
  ).join('$$$');
  return JSON.stringify({
    list: [{
      vod_id: id,
      'vod_name': (html.match(/<title>(.*?)-.*?<\/title>/) || ["", ""])[1],
      'vod_pic': (html.match(/data-original="(.*?)"/) || ["", ""])[1],
      vod_year: (html.match(/<a href="\/gqsc\/-------------.*?.html" target="_blank">(.*?)<\/a>/) || ["", ""])[1],
      vod_area: (html.match(/<a href="\/gqsc\/--.*?-----------.html" target="_blank">(.*?)<\/a>/) || ["", ""])[1],
      vod_remarks: (html.match(/<p class="data">更新：(.*?)<\/p>/) || ["", ""])[1],
      'type_name': (html.match(/<a href="\/vodtype\/.*?>分类：(.*?)<\/a>/) || ["", ""])[1],
      vod_actor: Array.from(
        html.match(/<p class="data">\s*主演：([\s\S]*?)<\/p>/)?.[1]?.matchAll(/<a [^>]*>([^<]+)<\/a>/g) || []).map(m => m[1]).join(' / ') || '',
      vod_director: Array.from(
        html.match(/<p class="data">\s*导演：([\s\S]*?)<\/p>/)?.[1]?.matchAll(/<a [^>]*>([^<]+)<\/a>/g) || []).map(m => m[1]).join(' / ') || '',
      'vod_content': "📢:本资源来源于网络🚓侵权请联系删除👉" + (html.match(/<meta name="description" content="([\s\S]*?)/) || ["", ""])[1].replace(/<.*?>/g, "").replace("特别提醒如果您对影片有自己的看法请留言弹幕评论。", ""),
      vod_play_from: "不良AV专线",
      vod_play_url: playUrl
    }]
  });
}
async function search(wd, quick, pg) {
  let p = pg || 1;
  let url = host + "/vodsearch/" + encodeURIComponent(wd) + "----------" + (parseInt(p) > 1 ? parseInt(p) + "---.html" : "1---.html");

  let resp = await req(url, {
    headers
  });
  return JSON.stringify({
    list: getList(resp.content)
  });
}
async function play(flag, id, flags) {
  let url = host + id;
  let resp = await req(url, {
    headers
  });
  let m3u8 = resp.content.match(/"url":"([^"]+\.m3u8)"/);
  if (m3u8) {
    return JSON.stringify({
      parse: 0,
      url: m3u8[1].replace(/\\/g, ""),
      header: headers
    });
  }
  let jump = resp.content.match(/(?:iframe|video)\s+[^>]*\bsrc\s*=\s*["']([^"']+\.m3u8(?:\?[^"']*)?)["']/i) ||
    resp.content.match(/location\.href\s*=\s*["']([^"']+\.m3u8(?:\?[^"']*)?)["']/i);
  if (jump) {
    let realUrl = jump[1].startsWith("http") ? jump[1] : host + jump[1];
    return JSON.stringify({
      parse: 0,
      url: realUrl,
      header: headers
    });
  }
  return JSON.stringify({
    parse: 1,
    url: url,
    header: headers
  });
}
export default {
  init,
  home,
  homeVod,
  category,
  detail,
  search,
  play
};
