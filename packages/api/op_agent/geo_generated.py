"""自動產生，請勿手改。

來源：(統一資訊) 命題數據集 - 2026 雲湧智生：臺灣生成式 AI 應用黑客松競賽/縣市區域範例資料.json
重新產生：python scripts/gen_geo.py
對應 sys_county / sys_district（縣市代碼 2 碼、行政區代碼 3 碼）
"""

from __future__ import annotations

from typing import TypedDict


class CountyRow(TypedDict):
    code: str
    name: str


class DistrictRow(TypedDict):
    code: str
    county_code: str
    name: str
    zip: str


COUNTIES: list[CountyRow] = [
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
]

DISTRICTS: list[DistrictRow] = [
    {
        "code": "001",
        "county_code": "01",
        "name": "中正區",
        "zip": "100"
    },
    {
        "code": "002",
        "county_code": "01",
        "name": "大同區",
        "zip": "103"
    },
    {
        "code": "003",
        "county_code": "01",
        "name": "中山區",
        "zip": "104"
    },
    {
        "code": "004",
        "county_code": "01",
        "name": "萬華區",
        "zip": "108"
    },
    {
        "code": "005",
        "county_code": "01",
        "name": "信義區",
        "zip": "110"
    },
    {
        "code": "006",
        "county_code": "01",
        "name": "松山區",
        "zip": "105"
    },
    {
        "code": "007",
        "county_code": "01",
        "name": "大安區",
        "zip": "106"
    },
    {
        "code": "008",
        "county_code": "01",
        "name": "南港區",
        "zip": "115"
    },
    {
        "code": "009",
        "county_code": "01",
        "name": "北投區",
        "zip": "112"
    },
    {
        "code": "010",
        "county_code": "01",
        "name": "內湖區",
        "zip": "114"
    },
    {
        "code": "011",
        "county_code": "01",
        "name": "士林區",
        "zip": "111"
    },
    {
        "code": "012",
        "county_code": "01",
        "name": "文山區",
        "zip": "116"
    },
    {
        "code": "013",
        "county_code": "02",
        "name": "板橋區",
        "zip": "220"
    },
    {
        "code": "014",
        "county_code": "02",
        "name": "新莊區",
        "zip": "242"
    },
    {
        "code": "015",
        "county_code": "02",
        "name": "泰山區",
        "zip": "243"
    },
    {
        "code": "016",
        "county_code": "02",
        "name": "林口區",
        "zip": "244"
    },
    {
        "code": "017",
        "county_code": "02",
        "name": "淡水區",
        "zip": "251"
    },
    {
        "code": "018",
        "county_code": "02",
        "name": "金山區",
        "zip": "208"
    },
    {
        "code": "019",
        "county_code": "02",
        "name": "八里區",
        "zip": "249"
    },
    {
        "code": "020",
        "county_code": "02",
        "name": "萬里區",
        "zip": "207"
    },
    {
        "code": "021",
        "county_code": "02",
        "name": "石門區",
        "zip": "253"
    },
    {
        "code": "022",
        "county_code": "02",
        "name": "三芝區",
        "zip": "252"
    },
    {
        "code": "023",
        "county_code": "02",
        "name": "瑞芳區",
        "zip": "224"
    },
    {
        "code": "024",
        "county_code": "02",
        "name": "汐止區",
        "zip": "221"
    },
    {
        "code": "025",
        "county_code": "02",
        "name": "平溪區",
        "zip": "226"
    },
    {
        "code": "026",
        "county_code": "02",
        "name": "貢寮區",
        "zip": "228"
    },
    {
        "code": "027",
        "county_code": "02",
        "name": "雙溪區",
        "zip": "227"
    },
    {
        "code": "028",
        "county_code": "02",
        "name": "深坑區",
        "zip": "222"
    },
    {
        "code": "029",
        "county_code": "02",
        "name": "石碇區",
        "zip": "223"
    },
    {
        "code": "030",
        "county_code": "02",
        "name": "新店區",
        "zip": "231"
    },
    {
        "code": "031",
        "county_code": "02",
        "name": "坪林區",
        "zip": "232"
    },
    {
        "code": "032",
        "county_code": "02",
        "name": "烏來區",
        "zip": "233"
    },
    {
        "code": "033",
        "county_code": "02",
        "name": "中和區",
        "zip": "235"
    },
    {
        "code": "034",
        "county_code": "02",
        "name": "永和區",
        "zip": "234"
    },
    {
        "code": "035",
        "county_code": "02",
        "name": "土城區",
        "zip": "236"
    },
    {
        "code": "036",
        "county_code": "02",
        "name": "三峽區",
        "zip": "237"
    },
    {
        "code": "037",
        "county_code": "02",
        "name": "樹林區",
        "zip": "238"
    },
    {
        "code": "038",
        "county_code": "02",
        "name": "鶯歌區",
        "zip": "239"
    },
    {
        "code": "039",
        "county_code": "02",
        "name": "三重區",
        "zip": "241"
    },
    {
        "code": "040",
        "county_code": "02",
        "name": "蘆洲區",
        "zip": "247"
    },
    {
        "code": "041",
        "county_code": "02",
        "name": "五股區",
        "zip": "248"
    },
    {
        "code": "042",
        "county_code": "03",
        "name": "仁愛區",
        "zip": "200"
    },
    {
        "code": "043",
        "county_code": "03",
        "name": "中正區",
        "zip": "202"
    },
    {
        "code": "044",
        "county_code": "03",
        "name": "信義區",
        "zip": "201"
    },
    {
        "code": "045",
        "county_code": "03",
        "name": "中山區",
        "zip": "203"
    },
    {
        "code": "046",
        "county_code": "03",
        "name": "安樂區",
        "zip": "204"
    },
    {
        "code": "047",
        "county_code": "03",
        "name": "暖暖區",
        "zip": "205"
    },
    {
        "code": "048",
        "county_code": "03",
        "name": "七堵區",
        "zip": "206"
    },
    {
        "code": "049",
        "county_code": "04",
        "name": "桃園區",
        "zip": "330"
    },
    {
        "code": "050",
        "county_code": "04",
        "name": "中壢區",
        "zip": "320"
    },
    {
        "code": "051",
        "county_code": "04",
        "name": "平鎮區",
        "zip": "324"
    },
    {
        "code": "052",
        "county_code": "04",
        "name": "八德區",
        "zip": "334"
    },
    {
        "code": "053",
        "county_code": "04",
        "name": "楊梅區",
        "zip": "326"
    },
    {
        "code": "054",
        "county_code": "04",
        "name": "蘆竹區",
        "zip": "338"
    },
    {
        "code": "055",
        "county_code": "04",
        "name": "龜山區",
        "zip": "333"
    },
    {
        "code": "056",
        "county_code": "04",
        "name": "龍潭區",
        "zip": "325"
    },
    {
        "code": "057",
        "county_code": "04",
        "name": "大溪區",
        "zip": "335"
    },
    {
        "code": "058",
        "county_code": "04",
        "name": "大園區",
        "zip": "337"
    },
    {
        "code": "059",
        "county_code": "04",
        "name": "觀音區",
        "zip": "328"
    },
    {
        "code": "060",
        "county_code": "04",
        "name": "新屋區",
        "zip": "327"
    },
    {
        "code": "061",
        "county_code": "04",
        "name": "復興區",
        "zip": "336"
    },
    {
        "code": "062",
        "county_code": "05",
        "name": "竹北市",
        "zip": "302"
    },
    {
        "code": "063",
        "county_code": "05",
        "name": "竹東鎮",
        "zip": "310"
    },
    {
        "code": "064",
        "county_code": "05",
        "name": "新埔鎮",
        "zip": "305"
    },
    {
        "code": "065",
        "county_code": "05",
        "name": "關西鎮",
        "zip": "306"
    },
    {
        "code": "066",
        "county_code": "05",
        "name": "峨眉鄉",
        "zip": "315"
    },
    {
        "code": "067",
        "county_code": "05",
        "name": "寶山鄉",
        "zip": "308"
    },
    {
        "code": "068",
        "county_code": "05",
        "name": "北埔鄉",
        "zip": "314"
    },
    {
        "code": "069",
        "county_code": "05",
        "name": "橫山鄉",
        "zip": "312"
    },
    {
        "code": "238",
        "county_code": "14",
        "name": "山上區",
        "zip": "743"
    },
    {
        "code": "239",
        "county_code": "14",
        "name": "新市區",
        "zip": "744"
    },
    {
        "code": "240",
        "county_code": "14",
        "name": "安定區",
        "zip": "745"
    },
    {
        "code": "241",
        "county_code": "15",
        "name": "楠梓區",
        "zip": "811"
    },
    {
        "code": "242",
        "county_code": "15",
        "name": "左營區",
        "zip": "813"
    },
    {
        "code": "243",
        "county_code": "15",
        "name": "鼓山區",
        "zip": "804"
    },
    {
        "code": "244",
        "county_code": "15",
        "name": "三民區",
        "zip": "807"
    },
    {
        "code": "245",
        "county_code": "15",
        "name": "鹽埕區",
        "zip": "803"
    },
    {
        "code": "246",
        "county_code": "15",
        "name": "前金區",
        "zip": "801"
    },
    {
        "code": "247",
        "county_code": "15",
        "name": "新興區",
        "zip": "800"
    },
    {
        "code": "248",
        "county_code": "15",
        "name": "苓雅區",
        "zip": "802"
    },
    {
        "code": "249",
        "county_code": "15",
        "name": "前鎮區",
        "zip": "806"
    },
    {
        "code": "250",
        "county_code": "15",
        "name": "小港區",
        "zip": "812"
    },
    {
        "code": "251",
        "county_code": "15",
        "name": "旗津區",
        "zip": "805"
    },
    {
        "code": "252",
        "county_code": "15",
        "name": "鳳山區",
        "zip": "830"
    },
    {
        "code": "253",
        "county_code": "15",
        "name": "大寮區",
        "zip": "831"
    },
    {
        "code": "254",
        "county_code": "15",
        "name": "鳥松區",
        "zip": "833"
    },
    {
        "code": "255",
        "county_code": "15",
        "name": "林園區",
        "zip": "832"
    },
    {
        "code": "256",
        "county_code": "15",
        "name": "仁武區",
        "zip": "814"
    },
    {
        "code": "257",
        "county_code": "15",
        "name": "大樹區",
        "zip": "840"
    },
    {
        "code": "258",
        "county_code": "15",
        "name": "大社區",
        "zip": "815"
    },
    {
        "code": "259",
        "county_code": "15",
        "name": "岡山區",
        "zip": "820"
    },
    {
        "code": "260",
        "county_code": "15",
        "name": "路竹區",
        "zip": "821"
    },
    {
        "code": "261",
        "county_code": "15",
        "name": "橋頭區",
        "zip": "825"
    },
    {
        "code": "262",
        "county_code": "15",
        "name": "梓官區",
        "zip": "826"
    },
    {
        "code": "263",
        "county_code": "15",
        "name": "彌陀區",
        "zip": "827"
    },
    {
        "code": "264",
        "county_code": "15",
        "name": "永安區",
        "zip": "828"
    },
    {
        "code": "265",
        "county_code": "15",
        "name": "燕巢區",
        "zip": "824"
    },
    {
        "code": "266",
        "county_code": "15",
        "name": "田寮區",
        "zip": "823"
    },
    {
        "code": "267",
        "county_code": "15",
        "name": "阿蓮區",
        "zip": "822"
    },
    {
        "code": "268",
        "county_code": "15",
        "name": "茄萣區",
        "zip": "852"
    },
    {
        "code": "269",
        "county_code": "15",
        "name": "湖內區",
        "zip": "829"
    },
    {
        "code": "270",
        "county_code": "15",
        "name": "旗山區",
        "zip": "842"
    },
    {
        "code": "271",
        "county_code": "15",
        "name": "美濃區",
        "zip": "843"
    },
    {
        "code": "272",
        "county_code": "15",
        "name": "內門區",
        "zip": "845"
    },
    {
        "code": "273",
        "county_code": "15",
        "name": "杉林區",
        "zip": "846"
    },
    {
        "code": "274",
        "county_code": "15",
        "name": "甲仙區",
        "zip": "847"
    },
    {
        "code": "275",
        "county_code": "15",
        "name": "六龜區",
        "zip": "844"
    },
    {
        "code": "276",
        "county_code": "15",
        "name": "茂林區",
        "zip": "851"
    },
    {
        "code": "277",
        "county_code": "15",
        "name": "桃源區",
        "zip": "848"
    },
    {
        "code": "278",
        "county_code": "15",
        "name": "那瑪夏區",
        "zip": "849"
    },
    {
        "code": "279",
        "county_code": "16",
        "name": "屏東市",
        "zip": "900"
    },
    {
        "code": "280",
        "county_code": "16",
        "name": "潮州鎮",
        "zip": "920"
    },
    {
        "code": "281",
        "county_code": "16",
        "name": "東港鎮",
        "zip": "928"
    },
    {
        "code": "282",
        "county_code": "16",
        "name": "恆春鎮",
        "zip": "946"
    },
    {
        "code": "283",
        "county_code": "16",
        "name": "萬丹鄉",
        "zip": "913"
    },
    {
        "code": "284",
        "county_code": "16",
        "name": "長治鄉",
        "zip": "908"
    },
    {
        "code": "285",
        "county_code": "16",
        "name": "麟洛鄉",
        "zip": "909"
    },
    {
        "code": "286",
        "county_code": "16",
        "name": "九如鄉",
        "zip": "904"
    },
    {
        "code": "287",
        "county_code": "16",
        "name": "里港鄉",
        "zip": "905"
    },
    {
        "code": "288",
        "county_code": "16",
        "name": "鹽埔鄉",
        "zip": "907"
    },
    {
        "code": "289",
        "county_code": "16",
        "name": "高樹鄉",
        "zip": "906"
    },
    {
        "code": "290",
        "county_code": "16",
        "name": "萬巒鄉",
        "zip": "923"
    },
    {
        "code": "291",
        "county_code": "16",
        "name": "內埔鄉",
        "zip": "912"
    },
    {
        "code": "292",
        "county_code": "16",
        "name": "竹田鄉",
        "zip": "911"
    },
    {
        "code": "293",
        "county_code": "16",
        "name": "新埤鄉",
        "zip": "925"
    },
    {
        "code": "294",
        "county_code": "16",
        "name": "枋寮鄉",
        "zip": "940"
    },
    {
        "code": "295",
        "county_code": "16",
        "name": "新園鄉",
        "zip": "932"
    },
    {
        "code": "296",
        "county_code": "16",
        "name": "崁頂鄉",
        "zip": "924"
    },
    {
        "code": "297",
        "county_code": "16",
        "name": "林邊鄉",
        "zip": "927"
    },
    {
        "code": "298",
        "county_code": "16",
        "name": "南州鄉",
        "zip": "926"
    },
    {
        "code": "299",
        "county_code": "16",
        "name": "佳冬鄉",
        "zip": "931"
    },
    {
        "code": "300",
        "county_code": "16",
        "name": "琉球鄉",
        "zip": "929"
    },
    {
        "code": "301",
        "county_code": "16",
        "name": "車城鄉",
        "zip": "944"
    },
    {
        "code": "302",
        "county_code": "16",
        "name": "滿州鄉",
        "zip": "947"
    },
    {
        "code": "303",
        "county_code": "16",
        "name": "枋山鄉",
        "zip": "941"
    },
    {
        "code": "304",
        "county_code": "16",
        "name": "霧台鄉",
        "zip": "902"
    },
    {
        "code": "305",
        "county_code": "16",
        "name": "瑪家鄉",
        "zip": "903"
    },
    {
        "code": "306",
        "county_code": "16",
        "name": "泰武鄉",
        "zip": "921"
    },
    {
        "code": "307",
        "county_code": "16",
        "name": "來義鄉",
        "zip": "922"
    },
    {
        "code": "308",
        "county_code": "16",
        "name": "春日鄉",
        "zip": "942"
    },
    {
        "code": "309",
        "county_code": "16",
        "name": "獅子鄉",
        "zip": "943"
    },
    {
        "code": "310",
        "county_code": "16",
        "name": "牡丹鄉",
        "zip": "945"
    },
    {
        "code": "311",
        "county_code": "16",
        "name": "三地門鄉",
        "zip": "901"
    },
    {
        "code": "312",
        "county_code": "17",
        "name": "宜蘭市",
        "zip": "260"
    },
    {
        "code": "313",
        "county_code": "17",
        "name": "羅東鎮",
        "zip": "265"
    },
    {
        "code": "314",
        "county_code": "17",
        "name": "蘇澳鎮",
        "zip": "270"
    },
    {
        "code": "315",
        "county_code": "17",
        "name": "頭城鎮",
        "zip": "261"
    },
    {
        "code": "316",
        "county_code": "17",
        "name": "礁溪鄉",
        "zip": "262"
    },
    {
        "code": "317",
        "county_code": "17",
        "name": "壯圍鄉",
        "zip": "263"
    },
    {
        "code": "318",
        "county_code": "17",
        "name": "員山鄉",
        "zip": "264"
    },
    {
        "code": "319",
        "county_code": "17",
        "name": "冬山鄉",
        "zip": "269"
    },
    {
        "code": "320",
        "county_code": "17",
        "name": "五結鄉",
        "zip": "268"
    },
    {
        "code": "321",
        "county_code": "17",
        "name": "三星鄉",
        "zip": "266"
    },
    {
        "code": "322",
        "county_code": "17",
        "name": "大同鄉",
        "zip": "267"
    },
    {
        "code": "323",
        "county_code": "17",
        "name": "南澳鄉",
        "zip": "272"
    },
    {
        "code": "324",
        "county_code": "18",
        "name": "花蓮市",
        "zip": "970"
    },
    {
        "code": "325",
        "county_code": "18",
        "name": "鳳林鎮",
        "zip": "975"
    },
    {
        "code": "326",
        "county_code": "18",
        "name": "玉里鎮",
        "zip": "981"
    },
    {
        "code": "327",
        "county_code": "18",
        "name": "新城鄉",
        "zip": "971"
    },
    {
        "code": "328",
        "county_code": "18",
        "name": "吉安鄉",
        "zip": "973"
    },
    {
        "code": "329",
        "county_code": "18",
        "name": "壽豐鄉",
        "zip": "974"
    },
    {
        "code": "330",
        "county_code": "18",
        "name": "秀林鄉",
        "zip": "972"
    },
    {
        "code": "331",
        "county_code": "18",
        "name": "光復鄉",
        "zip": "976"
    },
    {
        "code": "332",
        "county_code": "18",
        "name": "豐濱鄉",
        "zip": "977"
    },
    {
        "code": "333",
        "county_code": "18",
        "name": "瑞穗鄉",
        "zip": "978"
    },
    {
        "code": "334",
        "county_code": "18",
        "name": "萬榮鄉",
        "zip": "979"
    },
    {
        "code": "335",
        "county_code": "18",
        "name": "富里鄉",
        "zip": "983"
    },
    {
        "code": "336",
        "county_code": "18",
        "name": "卓溪鄉",
        "zip": "982"
    },
    {
        "code": "337",
        "county_code": "19",
        "name": "台東市",
        "zip": "950"
    },
    {
        "code": "338",
        "county_code": "19",
        "name": "成功鎮",
        "zip": "961"
    },
    {
        "code": "339",
        "county_code": "19",
        "name": "關山鎮",
        "zip": "956"
    },
    {
        "code": "340",
        "county_code": "19",
        "name": "長濱鄉",
        "zip": "962"
    },
    {
        "code": "341",
        "county_code": "19",
        "name": "海端鄉",
        "zip": "957"
    },
    {
        "code": "342",
        "county_code": "19",
        "name": "池上鄉",
        "zip": "958"
    },
    {
        "code": "343",
        "county_code": "19",
        "name": "東河鄉",
        "zip": "959"
    },
    {
        "code": "344",
        "county_code": "19",
        "name": "鹿野鄉",
        "zip": "955"
    },
    {
        "code": "345",
        "county_code": "19",
        "name": "延平鄉",
        "zip": "953"
    },
    {
        "code": "346",
        "county_code": "19",
        "name": "卑南鄉",
        "zip": "954"
    },
    {
        "code": "347",
        "county_code": "19",
        "name": "金峰鄉",
        "zip": "964"
    },
    {
        "code": "348",
        "county_code": "19",
        "name": "大武鄉",
        "zip": "965"
    },
    {
        "code": "349",
        "county_code": "19",
        "name": "達仁鄉",
        "zip": "966"
    },
    {
        "code": "350",
        "county_code": "19",
        "name": "綠島鄉",
        "zip": "951"
    },
    {
        "code": "351",
        "county_code": "19",
        "name": "蘭嶼鄉",
        "zip": "952"
    },
    {
        "code": "352",
        "county_code": "19",
        "name": "太麻里鄉",
        "zip": "963"
    },
    {
        "code": "353",
        "county_code": "20",
        "name": "馬公市",
        "zip": "880"
    },
    {
        "code": "354",
        "county_code": "20",
        "name": "湖西鄉",
        "zip": "885"
    },
    {
        "code": "355",
        "county_code": "20",
        "name": "白沙鄉",
        "zip": "884"
    },
    {
        "code": "356",
        "county_code": "20",
        "name": "西嶼鄉",
        "zip": "881"
    },
    {
        "code": "357",
        "county_code": "20",
        "name": "望安鄉",
        "zip": "882"
    },
    {
        "code": "358",
        "county_code": "20",
        "name": "七美鄉",
        "zip": "883"
    },
    {
        "code": "359",
        "county_code": "21",
        "name": "金城鎮",
        "zip": "893"
    },
    {
        "code": "360",
        "county_code": "21",
        "name": "金湖鎮",
        "zip": "891"
    },
    {
        "code": "361",
        "county_code": "21",
        "name": "金沙鎮",
        "zip": "890"
    },
    {
        "code": "362",
        "county_code": "21",
        "name": "金寧鄉",
        "zip": "892"
    },
    {
        "code": "363",
        "county_code": "21",
        "name": "烈嶼鄉",
        "zip": "894"
    },
    {
        "code": "364",
        "county_code": "21",
        "name": "烏坵鄉",
        "zip": "896"
    },
    {
        "code": "365",
        "county_code": "22",
        "name": "南竿鄉",
        "zip": "209"
    },
    {
        "code": "366",
        "county_code": "22",
        "name": "北竿鄉",
        "zip": "210"
    },
    {
        "code": "367",
        "county_code": "22",
        "name": "莒光鄉",
        "zip": "211"
    },
    {
        "code": "368",
        "county_code": "22",
        "name": "東引鄉",
        "zip": "212"
    }
]
