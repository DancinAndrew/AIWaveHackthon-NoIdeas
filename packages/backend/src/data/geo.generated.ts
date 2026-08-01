/**
 * 自動產生，請勿手改。來源：(統一資訊) 命題數據集 - 2026 雲湧智生：臺灣生成式 AI 應用黑客松競賽/縣市區域範例資料.json
 * 重新產生：node scripts/gen-geo.mjs
 * sys_county / sys_district（縣市代碼 2 碼、行政區代碼 3 碼）
 */

export interface CountyRow {
  code: string;
  name: string;
}

export interface DistrictRow {
  code: string;
  countyCode: string;
  name: string;
  zip: string;
}

export const COUNTIES: CountyRow[] = [
  {
    "code": "01",
    "name": "台北市"
  },
  {
    "code": "02",
    "name": "新北市"
  },
  {
    "code": "03",
    "name": "基隆市"
  },
  {
    "code": "04",
    "name": "桃園市"
  },
  {
    "code": "05",
    "name": "新竹縣"
  },
  {
    "code": "06",
    "name": "新竹市"
  },
  {
    "code": "07",
    "name": "苗栗縣"
  },
  {
    "code": "08",
    "name": "台中市"
  },
  {
    "code": "09",
    "name": "南投縣"
  },
  {
    "code": "10",
    "name": "彰化縣"
  },
  {
    "code": "11",
    "name": "雲林縣"
  },
  {
    "code": "12",
    "name": "嘉義縣"
  },
  {
    "code": "13",
    "name": "嘉義市"
  },
  {
    "code": "14",
    "name": "台南市"
  },
  {
    "code": "15",
    "name": "高雄市"
  },
  {
    "code": "16",
    "name": "屏東縣"
  },
  {
    "code": "17",
    "name": "宜蘭縣"
  },
  {
    "code": "18",
    "name": "花蓮縣"
  },
  {
    "code": "19",
    "name": "台東縣"
  },
  {
    "code": "20",
    "name": "澎湖縣"
  },
  {
    "code": "21",
    "name": "金門縣"
  },
  {
    "code": "22",
    "name": "連江縣"
  }
];

export const DISTRICTS: DistrictRow[] = [
  {
    "code": "001",
    "countyCode": "01",
    "name": "中正區",
    "zip": "100"
  },
  {
    "code": "002",
    "countyCode": "01",
    "name": "大同區",
    "zip": "103"
  },
  {
    "code": "003",
    "countyCode": "01",
    "name": "中山區",
    "zip": "104"
  },
  {
    "code": "004",
    "countyCode": "01",
    "name": "萬華區",
    "zip": "108"
  },
  {
    "code": "005",
    "countyCode": "01",
    "name": "信義區",
    "zip": "110"
  },
  {
    "code": "006",
    "countyCode": "01",
    "name": "松山區",
    "zip": "105"
  },
  {
    "code": "007",
    "countyCode": "01",
    "name": "大安區",
    "zip": "106"
  },
  {
    "code": "008",
    "countyCode": "01",
    "name": "南港區",
    "zip": "115"
  },
  {
    "code": "009",
    "countyCode": "01",
    "name": "北投區",
    "zip": "112"
  },
  {
    "code": "010",
    "countyCode": "01",
    "name": "內湖區",
    "zip": "114"
  },
  {
    "code": "011",
    "countyCode": "01",
    "name": "士林區",
    "zip": "111"
  },
  {
    "code": "012",
    "countyCode": "01",
    "name": "文山區",
    "zip": "116"
  },
  {
    "code": "013",
    "countyCode": "02",
    "name": "板橋區",
    "zip": "220"
  },
  {
    "code": "014",
    "countyCode": "02",
    "name": "新莊區",
    "zip": "242"
  },
  {
    "code": "015",
    "countyCode": "02",
    "name": "泰山區",
    "zip": "243"
  },
  {
    "code": "016",
    "countyCode": "02",
    "name": "林口區",
    "zip": "244"
  },
  {
    "code": "017",
    "countyCode": "02",
    "name": "淡水區",
    "zip": "251"
  },
  {
    "code": "018",
    "countyCode": "02",
    "name": "金山區",
    "zip": "208"
  },
  {
    "code": "019",
    "countyCode": "02",
    "name": "八里區",
    "zip": "249"
  },
  {
    "code": "020",
    "countyCode": "02",
    "name": "萬里區",
    "zip": "207"
  },
  {
    "code": "021",
    "countyCode": "02",
    "name": "石門區",
    "zip": "253"
  },
  {
    "code": "022",
    "countyCode": "02",
    "name": "三芝區",
    "zip": "252"
  },
  {
    "code": "023",
    "countyCode": "02",
    "name": "瑞芳區",
    "zip": "224"
  },
  {
    "code": "024",
    "countyCode": "02",
    "name": "汐止區",
    "zip": "221"
  },
  {
    "code": "025",
    "countyCode": "02",
    "name": "平溪區",
    "zip": "226"
  },
  {
    "code": "026",
    "countyCode": "02",
    "name": "貢寮區",
    "zip": "228"
  },
  {
    "code": "027",
    "countyCode": "02",
    "name": "雙溪區",
    "zip": "227"
  },
  {
    "code": "028",
    "countyCode": "02",
    "name": "深坑區",
    "zip": "222"
  },
  {
    "code": "029",
    "countyCode": "02",
    "name": "石碇區",
    "zip": "223"
  },
  {
    "code": "030",
    "countyCode": "02",
    "name": "新店區",
    "zip": "231"
  },
  {
    "code": "031",
    "countyCode": "02",
    "name": "坪林區",
    "zip": "232"
  },
  {
    "code": "032",
    "countyCode": "02",
    "name": "烏來區",
    "zip": "233"
  },
  {
    "code": "033",
    "countyCode": "02",
    "name": "中和區",
    "zip": "235"
  },
  {
    "code": "034",
    "countyCode": "02",
    "name": "永和區",
    "zip": "234"
  },
  {
    "code": "035",
    "countyCode": "02",
    "name": "土城區",
    "zip": "236"
  },
  {
    "code": "036",
    "countyCode": "02",
    "name": "三峽區",
    "zip": "237"
  },
  {
    "code": "037",
    "countyCode": "02",
    "name": "樹林區",
    "zip": "238"
  },
  {
    "code": "038",
    "countyCode": "02",
    "name": "鶯歌區",
    "zip": "239"
  },
  {
    "code": "039",
    "countyCode": "02",
    "name": "三重區",
    "zip": "241"
  },
  {
    "code": "040",
    "countyCode": "02",
    "name": "蘆洲區",
    "zip": "247"
  },
  {
    "code": "041",
    "countyCode": "02",
    "name": "五股區",
    "zip": "248"
  },
  {
    "code": "042",
    "countyCode": "03",
    "name": "仁愛區",
    "zip": "200"
  },
  {
    "code": "043",
    "countyCode": "03",
    "name": "中正區",
    "zip": "202"
  },
  {
    "code": "044",
    "countyCode": "03",
    "name": "信義區",
    "zip": "201"
  },
  {
    "code": "045",
    "countyCode": "03",
    "name": "中山區",
    "zip": "203"
  },
  {
    "code": "046",
    "countyCode": "03",
    "name": "安樂區",
    "zip": "204"
  },
  {
    "code": "047",
    "countyCode": "03",
    "name": "暖暖區",
    "zip": "205"
  },
  {
    "code": "048",
    "countyCode": "03",
    "name": "七堵區",
    "zip": "206"
  },
  {
    "code": "049",
    "countyCode": "04",
    "name": "桃園區",
    "zip": "330"
  },
  {
    "code": "050",
    "countyCode": "04",
    "name": "中壢區",
    "zip": "320"
  },
  {
    "code": "051",
    "countyCode": "04",
    "name": "平鎮區",
    "zip": "324"
  },
  {
    "code": "052",
    "countyCode": "04",
    "name": "八德區",
    "zip": "334"
  },
  {
    "code": "053",
    "countyCode": "04",
    "name": "楊梅區",
    "zip": "326"
  },
  {
    "code": "054",
    "countyCode": "04",
    "name": "蘆竹區",
    "zip": "338"
  },
  {
    "code": "055",
    "countyCode": "04",
    "name": "龜山區",
    "zip": "333"
  },
  {
    "code": "056",
    "countyCode": "04",
    "name": "龍潭區",
    "zip": "325"
  },
  {
    "code": "057",
    "countyCode": "04",
    "name": "大溪區",
    "zip": "335"
  },
  {
    "code": "058",
    "countyCode": "04",
    "name": "大園區",
    "zip": "337"
  },
  {
    "code": "059",
    "countyCode": "04",
    "name": "觀音區",
    "zip": "328"
  },
  {
    "code": "060",
    "countyCode": "04",
    "name": "新屋區",
    "zip": "327"
  },
  {
    "code": "061",
    "countyCode": "04",
    "name": "復興區",
    "zip": "336"
  },
  {
    "code": "062",
    "countyCode": "05",
    "name": "竹北市",
    "zip": "302"
  },
  {
    "code": "063",
    "countyCode": "05",
    "name": "竹東鎮",
    "zip": "310"
  },
  {
    "code": "064",
    "countyCode": "05",
    "name": "新埔鎮",
    "zip": "305"
  },
  {
    "code": "065",
    "countyCode": "05",
    "name": "關西鎮",
    "zip": "306"
  },
  {
    "code": "066",
    "countyCode": "05",
    "name": "峨眉鄉",
    "zip": "315"
  },
  {
    "code": "067",
    "countyCode": "05",
    "name": "寶山鄉",
    "zip": "308"
  },
  {
    "code": "068",
    "countyCode": "05",
    "name": "北埔鄉",
    "zip": "314"
  },
  {
    "code": "069",
    "countyCode": "05",
    "name": "橫山鄉",
    "zip": "312"
  },
  {
    "code": "238",
    "countyCode": "14",
    "name": "山上區",
    "zip": "743"
  },
  {
    "code": "239",
    "countyCode": "14",
    "name": "新市區",
    "zip": "744"
  },
  {
    "code": "240",
    "countyCode": "14",
    "name": "安定區",
    "zip": "745"
  },
  {
    "code": "241",
    "countyCode": "15",
    "name": "楠梓區",
    "zip": "811"
  },
  {
    "code": "242",
    "countyCode": "15",
    "name": "左營區",
    "zip": "813"
  },
  {
    "code": "243",
    "countyCode": "15",
    "name": "鼓山區",
    "zip": "804"
  },
  {
    "code": "244",
    "countyCode": "15",
    "name": "三民區",
    "zip": "807"
  },
  {
    "code": "245",
    "countyCode": "15",
    "name": "鹽埕區",
    "zip": "803"
  },
  {
    "code": "246",
    "countyCode": "15",
    "name": "前金區",
    "zip": "801"
  },
  {
    "code": "247",
    "countyCode": "15",
    "name": "新興區",
    "zip": "800"
  },
  {
    "code": "248",
    "countyCode": "15",
    "name": "苓雅區",
    "zip": "802"
  },
  {
    "code": "249",
    "countyCode": "15",
    "name": "前鎮區",
    "zip": "806"
  },
  {
    "code": "250",
    "countyCode": "15",
    "name": "小港區",
    "zip": "812"
  },
  {
    "code": "251",
    "countyCode": "15",
    "name": "旗津區",
    "zip": "805"
  },
  {
    "code": "252",
    "countyCode": "15",
    "name": "鳳山區",
    "zip": "830"
  },
  {
    "code": "253",
    "countyCode": "15",
    "name": "大寮區",
    "zip": "831"
  },
  {
    "code": "254",
    "countyCode": "15",
    "name": "鳥松區",
    "zip": "833"
  },
  {
    "code": "255",
    "countyCode": "15",
    "name": "林園區",
    "zip": "832"
  },
  {
    "code": "256",
    "countyCode": "15",
    "name": "仁武區",
    "zip": "814"
  },
  {
    "code": "257",
    "countyCode": "15",
    "name": "大樹區",
    "zip": "840"
  },
  {
    "code": "258",
    "countyCode": "15",
    "name": "大社區",
    "zip": "815"
  },
  {
    "code": "259",
    "countyCode": "15",
    "name": "岡山區",
    "zip": "820"
  },
  {
    "code": "260",
    "countyCode": "15",
    "name": "路竹區",
    "zip": "821"
  },
  {
    "code": "261",
    "countyCode": "15",
    "name": "橋頭區",
    "zip": "825"
  },
  {
    "code": "262",
    "countyCode": "15",
    "name": "梓官區",
    "zip": "826"
  },
  {
    "code": "263",
    "countyCode": "15",
    "name": "彌陀區",
    "zip": "827"
  },
  {
    "code": "264",
    "countyCode": "15",
    "name": "永安區",
    "zip": "828"
  },
  {
    "code": "265",
    "countyCode": "15",
    "name": "燕巢區",
    "zip": "824"
  },
  {
    "code": "266",
    "countyCode": "15",
    "name": "田寮區",
    "zip": "823"
  },
  {
    "code": "267",
    "countyCode": "15",
    "name": "阿蓮區",
    "zip": "822"
  },
  {
    "code": "268",
    "countyCode": "15",
    "name": "茄萣區",
    "zip": "852"
  },
  {
    "code": "269",
    "countyCode": "15",
    "name": "湖內區",
    "zip": "829"
  },
  {
    "code": "270",
    "countyCode": "15",
    "name": "旗山區",
    "zip": "842"
  },
  {
    "code": "271",
    "countyCode": "15",
    "name": "美濃區",
    "zip": "843"
  },
  {
    "code": "272",
    "countyCode": "15",
    "name": "內門區",
    "zip": "845"
  },
  {
    "code": "273",
    "countyCode": "15",
    "name": "杉林區",
    "zip": "846"
  },
  {
    "code": "274",
    "countyCode": "15",
    "name": "甲仙區",
    "zip": "847"
  },
  {
    "code": "275",
    "countyCode": "15",
    "name": "六龜區",
    "zip": "844"
  },
  {
    "code": "276",
    "countyCode": "15",
    "name": "茂林區",
    "zip": "851"
  },
  {
    "code": "277",
    "countyCode": "15",
    "name": "桃源區",
    "zip": "848"
  },
  {
    "code": "278",
    "countyCode": "15",
    "name": "那瑪夏區",
    "zip": "849"
  },
  {
    "code": "279",
    "countyCode": "16",
    "name": "屏東市",
    "zip": "900"
  },
  {
    "code": "280",
    "countyCode": "16",
    "name": "潮州鎮",
    "zip": "920"
  },
  {
    "code": "281",
    "countyCode": "16",
    "name": "東港鎮",
    "zip": "928"
  },
  {
    "code": "282",
    "countyCode": "16",
    "name": "恆春鎮",
    "zip": "946"
  },
  {
    "code": "283",
    "countyCode": "16",
    "name": "萬丹鄉",
    "zip": "913"
  },
  {
    "code": "284",
    "countyCode": "16",
    "name": "長治鄉",
    "zip": "908"
  },
  {
    "code": "285",
    "countyCode": "16",
    "name": "麟洛鄉",
    "zip": "909"
  },
  {
    "code": "286",
    "countyCode": "16",
    "name": "九如鄉",
    "zip": "904"
  },
  {
    "code": "287",
    "countyCode": "16",
    "name": "里港鄉",
    "zip": "905"
  },
  {
    "code": "288",
    "countyCode": "16",
    "name": "鹽埔鄉",
    "zip": "907"
  },
  {
    "code": "289",
    "countyCode": "16",
    "name": "高樹鄉",
    "zip": "906"
  },
  {
    "code": "290",
    "countyCode": "16",
    "name": "萬巒鄉",
    "zip": "923"
  },
  {
    "code": "291",
    "countyCode": "16",
    "name": "內埔鄉",
    "zip": "912"
  },
  {
    "code": "292",
    "countyCode": "16",
    "name": "竹田鄉",
    "zip": "911"
  },
  {
    "code": "293",
    "countyCode": "16",
    "name": "新埤鄉",
    "zip": "925"
  },
  {
    "code": "294",
    "countyCode": "16",
    "name": "枋寮鄉",
    "zip": "940"
  },
  {
    "code": "295",
    "countyCode": "16",
    "name": "新園鄉",
    "zip": "932"
  },
  {
    "code": "296",
    "countyCode": "16",
    "name": "崁頂鄉",
    "zip": "924"
  },
  {
    "code": "297",
    "countyCode": "16",
    "name": "林邊鄉",
    "zip": "927"
  },
  {
    "code": "298",
    "countyCode": "16",
    "name": "南州鄉",
    "zip": "926"
  },
  {
    "code": "299",
    "countyCode": "16",
    "name": "佳冬鄉",
    "zip": "931"
  },
  {
    "code": "300",
    "countyCode": "16",
    "name": "琉球鄉",
    "zip": "929"
  },
  {
    "code": "301",
    "countyCode": "16",
    "name": "車城鄉",
    "zip": "944"
  },
  {
    "code": "302",
    "countyCode": "16",
    "name": "滿州鄉",
    "zip": "947"
  },
  {
    "code": "303",
    "countyCode": "16",
    "name": "枋山鄉",
    "zip": "941"
  },
  {
    "code": "304",
    "countyCode": "16",
    "name": "霧台鄉",
    "zip": "902"
  },
  {
    "code": "305",
    "countyCode": "16",
    "name": "瑪家鄉",
    "zip": "903"
  },
  {
    "code": "306",
    "countyCode": "16",
    "name": "泰武鄉",
    "zip": "921"
  },
  {
    "code": "307",
    "countyCode": "16",
    "name": "來義鄉",
    "zip": "922"
  },
  {
    "code": "308",
    "countyCode": "16",
    "name": "春日鄉",
    "zip": "942"
  },
  {
    "code": "309",
    "countyCode": "16",
    "name": "獅子鄉",
    "zip": "943"
  },
  {
    "code": "310",
    "countyCode": "16",
    "name": "牡丹鄉",
    "zip": "945"
  },
  {
    "code": "311",
    "countyCode": "16",
    "name": "三地門鄉",
    "zip": "901"
  },
  {
    "code": "312",
    "countyCode": "17",
    "name": "宜蘭市",
    "zip": "260"
  },
  {
    "code": "313",
    "countyCode": "17",
    "name": "羅東鎮",
    "zip": "265"
  },
  {
    "code": "314",
    "countyCode": "17",
    "name": "蘇澳鎮",
    "zip": "270"
  },
  {
    "code": "315",
    "countyCode": "17",
    "name": "頭城鎮",
    "zip": "261"
  },
  {
    "code": "316",
    "countyCode": "17",
    "name": "礁溪鄉",
    "zip": "262"
  },
  {
    "code": "317",
    "countyCode": "17",
    "name": "壯圍鄉",
    "zip": "263"
  },
  {
    "code": "318",
    "countyCode": "17",
    "name": "員山鄉",
    "zip": "264"
  },
  {
    "code": "319",
    "countyCode": "17",
    "name": "冬山鄉",
    "zip": "269"
  },
  {
    "code": "320",
    "countyCode": "17",
    "name": "五結鄉",
    "zip": "268"
  },
  {
    "code": "321",
    "countyCode": "17",
    "name": "三星鄉",
    "zip": "266"
  },
  {
    "code": "322",
    "countyCode": "17",
    "name": "大同鄉",
    "zip": "267"
  },
  {
    "code": "323",
    "countyCode": "17",
    "name": "南澳鄉",
    "zip": "272"
  },
  {
    "code": "324",
    "countyCode": "18",
    "name": "花蓮市",
    "zip": "970"
  },
  {
    "code": "325",
    "countyCode": "18",
    "name": "鳳林鎮",
    "zip": "975"
  },
  {
    "code": "326",
    "countyCode": "18",
    "name": "玉里鎮",
    "zip": "981"
  },
  {
    "code": "327",
    "countyCode": "18",
    "name": "新城鄉",
    "zip": "971"
  },
  {
    "code": "328",
    "countyCode": "18",
    "name": "吉安鄉",
    "zip": "973"
  },
  {
    "code": "329",
    "countyCode": "18",
    "name": "壽豐鄉",
    "zip": "974"
  },
  {
    "code": "330",
    "countyCode": "18",
    "name": "秀林鄉",
    "zip": "972"
  },
  {
    "code": "331",
    "countyCode": "18",
    "name": "光復鄉",
    "zip": "976"
  },
  {
    "code": "332",
    "countyCode": "18",
    "name": "豐濱鄉",
    "zip": "977"
  },
  {
    "code": "333",
    "countyCode": "18",
    "name": "瑞穗鄉",
    "zip": "978"
  },
  {
    "code": "334",
    "countyCode": "18",
    "name": "萬榮鄉",
    "zip": "979"
  },
  {
    "code": "335",
    "countyCode": "18",
    "name": "富里鄉",
    "zip": "983"
  },
  {
    "code": "336",
    "countyCode": "18",
    "name": "卓溪鄉",
    "zip": "982"
  },
  {
    "code": "337",
    "countyCode": "19",
    "name": "台東市",
    "zip": "950"
  },
  {
    "code": "338",
    "countyCode": "19",
    "name": "成功鎮",
    "zip": "961"
  },
  {
    "code": "339",
    "countyCode": "19",
    "name": "關山鎮",
    "zip": "956"
  },
  {
    "code": "340",
    "countyCode": "19",
    "name": "長濱鄉",
    "zip": "962"
  },
  {
    "code": "341",
    "countyCode": "19",
    "name": "海端鄉",
    "zip": "957"
  },
  {
    "code": "342",
    "countyCode": "19",
    "name": "池上鄉",
    "zip": "958"
  },
  {
    "code": "343",
    "countyCode": "19",
    "name": "東河鄉",
    "zip": "959"
  },
  {
    "code": "344",
    "countyCode": "19",
    "name": "鹿野鄉",
    "zip": "955"
  },
  {
    "code": "345",
    "countyCode": "19",
    "name": "延平鄉",
    "zip": "953"
  },
  {
    "code": "346",
    "countyCode": "19",
    "name": "卑南鄉",
    "zip": "954"
  },
  {
    "code": "347",
    "countyCode": "19",
    "name": "金峰鄉",
    "zip": "964"
  },
  {
    "code": "348",
    "countyCode": "19",
    "name": "大武鄉",
    "zip": "965"
  },
  {
    "code": "349",
    "countyCode": "19",
    "name": "達仁鄉",
    "zip": "966"
  },
  {
    "code": "350",
    "countyCode": "19",
    "name": "綠島鄉",
    "zip": "951"
  },
  {
    "code": "351",
    "countyCode": "19",
    "name": "蘭嶼鄉",
    "zip": "952"
  },
  {
    "code": "352",
    "countyCode": "19",
    "name": "太麻里鄉",
    "zip": "963"
  },
  {
    "code": "353",
    "countyCode": "20",
    "name": "馬公市",
    "zip": "880"
  },
  {
    "code": "354",
    "countyCode": "20",
    "name": "湖西鄉",
    "zip": "885"
  },
  {
    "code": "355",
    "countyCode": "20",
    "name": "白沙鄉",
    "zip": "884"
  },
  {
    "code": "356",
    "countyCode": "20",
    "name": "西嶼鄉",
    "zip": "881"
  },
  {
    "code": "357",
    "countyCode": "20",
    "name": "望安鄉",
    "zip": "882"
  },
  {
    "code": "358",
    "countyCode": "20",
    "name": "七美鄉",
    "zip": "883"
  },
  {
    "code": "359",
    "countyCode": "21",
    "name": "金城鎮",
    "zip": "893"
  },
  {
    "code": "360",
    "countyCode": "21",
    "name": "金湖鎮",
    "zip": "891"
  },
  {
    "code": "361",
    "countyCode": "21",
    "name": "金沙鎮",
    "zip": "890"
  },
  {
    "code": "362",
    "countyCode": "21",
    "name": "金寧鄉",
    "zip": "892"
  },
  {
    "code": "363",
    "countyCode": "21",
    "name": "烈嶼鄉",
    "zip": "894"
  },
  {
    "code": "364",
    "countyCode": "21",
    "name": "烏坵鄉",
    "zip": "896"
  },
  {
    "code": "365",
    "countyCode": "22",
    "name": "南竿鄉",
    "zip": "209"
  },
  {
    "code": "366",
    "countyCode": "22",
    "name": "北竿鄉",
    "zip": "210"
  },
  {
    "code": "367",
    "countyCode": "22",
    "name": "莒光鄉",
    "zip": "211"
  },
  {
    "code": "368",
    "countyCode": "22",
    "name": "東引鄉",
    "zip": "212"
  }
];
