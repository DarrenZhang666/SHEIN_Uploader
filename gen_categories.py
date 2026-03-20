# -*- coding: utf-8 -*-
import json, os

def cat(id, name, kw, children=None):
    d = {"id": id, "name": name, "keywords": kw}
    if children:
        d["children"] = children
    return d

data = {
    "version": "1.0",
    "description": "SHEIN后台完整分类数据",
    "categories": [
        cat("women", "女装",
            ["women","woman","female","lady","ladies","dress","skirt","blouse","womens","女装","女士","女性","女生","连衣裙","半身裙","女"],
            [
                cat("women_dress", "连衣裙", ["dress","gown","frock","连衣裙","裙子"], [
                    cat("women_dress_mini","迷你裙",["mini dress","short dress","迷你裙","超短裙"]),
                    cat("women_dress_midi","中长裙",["midi dress","knee length","中长裙"]),
                    cat("women_dress_maxi","长连衣裙",["maxi dress","long dress","长连衣裙"]),
                    cat("women_dress_evening","晚礼服",["evening dress","formal dress","gown","晚礼服","礼服"]),
                    cat("women_dress_bodycon","修身连衣裙",["bodycon dress","tight dress","修身裙"]),
                    cat("women_dress_wrap","裹身裙",["wrap dress","裹身裙"]),
                    cat("women_dress_shirt","衬衫裙",["shirt dress","衬衫裙"]),
                    cat("women_dress_casual","休闲连衣裙",["casual dress","休闲裙"]),
                    cat("women_dress_knit","针织连衣裙",["knit dress","sweater dress","针织裙"]),
                    cat("women_dress_floral","碎花裙",["floral dress","flower dress","碎花裙","印花裙"]),
                ]),
                cat("women_skirt", "半身裙", ["skirt","half skirt","半身裙","短裙","a字裙"], [
                    cat("women_skirt_mini","超短裙",["mini skirt","超短裙"]),
                    cat("women_skirt_midi","中裙",["midi skirt","中裙"]),
                    cat("women_skirt_maxi","半身长裙",["maxi skirt","long skirt","半身长裙"]),
                    cat("women_skirt_aline","A字裙",["a-line skirt","a字裙"]),
                    cat("women_skirt_pleated","百褶裙",["pleated skirt","百褶裙"]),
                    cat("women_skirt_pencil","包臀裙",["pencil skirt","包臀裙"]),
                ]),
                cat("women_top", "上衣", ["top","blouse","shirt","tee","t-shirt","tshirt","tank","cami","上衣","t恤","衬衫","背心"], [
                    cat("women_top_tshirt","T恤",["t-shirt","tshirt","tee","t恤"]),
                    cat("women_top_blouse","衬衫",["blouse","shirt","衬衫"]),
                    cat("women_top_tank","背心",["tank top","cami","vest top","背心","吊带"]),
                    cat("women_top_crop","短款上衣",["crop top","短款上衣","露腰"]),
                    cat("women_top_knit","针织上衣",["knit top","针织上衣"]),
                    cat("women_top_polo","Polo衫",["polo shirt","polo衫"]),
                    cat("women_top_lace","蕾丝上衣",["lace top","蕾丝上衣"]),
                ]),
                cat("women_pants", "裤子", ["pants","trousers","leggings","jeans","shorts","裤子","长裤","短裤","牛仔裤","打底裤"], [
                    cat("women_pants_jeans","牛仔裤",["jeans","denim pants","牛仔裤"]),
                    cat("women_pants_trousers","休闲裤",["trousers","casual pants","休闲裤"]),
                    cat("women_pants_leggings","打底裤",["leggings","打底裤"]),
                    cat("women_pants_shorts","短裤",["shorts","短裤"]),
                    cat("women_pants_wide","阔腿裤",["wide leg pants","palazzo","阔腿裤"]),
                    cat("women_pants_skinny","铅笔裤",["skinny pants","slim pants","铅笔裤","紧身裤"]),
                    cat("women_pants_cargo","工装裤",["cargo pants","工装裤"]),
                    cat("women_pants_jogger","运动束脚裤",["jogger pants","sweatpants","运动裤","束脚裤"]),
                ]),
                cat("women_jacket", "外套", ["jacket","coat","blazer","cardigan","hoodie","sweatshirt","外套","夹克","大衣","风衣","卫衣"], [
                    cat("women_jacket_blazer","西装外套",["blazer","suit jacket","西装外套"]),
                    cat("women_jacket_trench","风衣",["trench coat","windbreaker","风衣"]),
                    cat("women_jacket_denim","牛仔外套",["denim jacket","jean jacket","牛仔外套"]),
                    cat("women_jacket_leather","皮夹克",["leather jacket","faux leather","皮夹克","pu外套"]),
                    cat("women_jacket_puffer","羽绒服",["puffer jacket","down jacket","quilted","羽绒服","棉服"]),
                    cat("women_jacket_cardigan","开衫",["cardigan","开衫","针织外套"]),
                    cat("women_jacket_hoodie","卫衣",["hoodie","sweatshirt","卫衣","套头衫"]),
                    cat("women_jacket_coat","大衣",["overcoat","大衣","长款外套"]),
                ]),
                cat("women_sweater", "毛衣针织", ["sweater","knit","knitwear","pullover","毛衣","针织衫"], [
                    cat("women_sweater_pullover","套头毛衣",["pullover","crewneck sweater","套头毛衣"]),
                    cat("women_sweater_turtleneck","高领毛衣",["turtleneck","mock neck","高领毛衣","高领"]),
                    cat("women_sweater_vneck","V领毛衣",["v-neck sweater","v领毛衣"]),
                ]),
                cat("women_suit", "套装", ["co-ord","matching set","套装","两件套"], [
                    cat("women_suit_pants","裤装套装",["pants suit","trouser suit","裤装套装"]),
                    cat("women_suit_skirt","裙装套装",["skirt suit","裙装套装"]),
                    cat("women_suit_twopiece","两件套",["two piece set","2 piece set","两件套"]),
                ]),
                cat("women_jumpsuit", "连体裤连体裙", ["jumpsuit","romper","playsuit","overalls","连体裤","连体裙"], [
                    cat("women_jumpsuit_long","连体长裤",["jumpsuit","连体裤"]),
                    cat("women_jumpsuit_short","连体短裤",["romper","playsuit","连体短裤"]),
                ]),
                cat("women_underwear", "内衣睡衣", ["underwear","bra","panty","pajamas","lingerie","sleepwear","nightgown","内衣","睡衣","文胸","内裤"], [
                    cat("women_bra","文胸",["bra","bralette","文胸","胸罩"]),
                    cat("women_panty","内裤",["panty","underwear","briefs","thong","内裤"]),
                    cat("women_pajamas","睡衣",["pajamas","sleepwear","nightgown","nightwear","睡衣","睡裙"]),
                    cat("women_lingerie","情趣内衣",["lingerie","sexy underwear","情趣内衣"]),
                ]),
            ]
        ),
        cat("men", "男装",
            ["men","man","male","guy","mens","men's","gentleman","男装","男士","男性","男生","男"],
            [
                cat("men_top", "上衣", ["men top","men shirt","men tee","男士上衣","男士衬衫","男士t恤"], [
                    cat("men_top_tshirt","T恤",["men t-shirt","men tee","男士t恤"]),
                    cat("men_top_shirt","衬衫",["men shirt","dress shirt","男士衬衫"]),
                    cat("men_top_polo","Polo衫",["men polo","polo shirt","男士polo"]),
                    cat("men_top_tank","背心",["men tank","men vest","男士背心"]),
                    cat("men_top_hoodie","卫衣",["men hoodie","men sweatshirt","男士卫衣"]),
                ]),
                cat("men_pants", "裤子", ["men pants","men trousers","men jeans","men shorts","男士裤子","男裤"], [
                    cat("men_pants_jeans","牛仔裤",["men jeans","男士牛仔裤"]),
                    cat("men_pants_trousers","休闲裤",["men trousers","men casual pants","男士休闲裤"]),
                    cat("men_pants_shorts","短裤",["men shorts","男士短裤"]),
                    cat("men_pants_cargo","工装裤",["men cargo","男士工装裤"]),
                    cat("men_pants_jogger","运动裤",["men jogger","men sweatpants","男士运动裤"]),
                ]),
                cat("men_jacket", "外套", ["men jacket","men coat","men blazer","男士外套","男士夹克"], [
                    cat("men_jacket_blazer","西装",["men blazer","men suit jacket","男士西装"]),
                    cat("men_jacket_denim","牛仔外套",["men denim jacket","男士牛仔外套"]),
                    cat("men_jacket_puffer","羽绒服",["men puffer jacket","men down jacket","男士羽绒服"]),
                    cat("men_jacket_hoodie","连帽卫衣",["men zip hoodie","男士连帽外套"]),
                    cat("men_jacket_windbreaker","风衣",["men windbreaker","men trench coat","男士风衣"]),
                ]),
                cat("men_suit", "西装套装", ["men suit","men formal","男士西装套装","男士正装"], [
                    cat("men_suit_full","整套西装",["men full suit","男士整套西装"]),
                    cat("men_suit_slim","修身西装",["men slim suit","男士修身西装"]),
                ]),
                cat("men_sweater", "毛衣", ["men sweater","men knitwear","men pullover","男士毛衣"], [
                    cat("men_sweater_crew","圆领毛衣",["men crew neck sweater","男士圆领毛衣"]),
                    cat("men_sweater_vneck","V领毛衣",["men v neck sweater","男士v领毛衣"]),
                ]),
            ]
        ),
        cat("kids", "童装",
            ["kids","children","child","baby","toddler","infant","boy","girl","youth","junior","童装","儿童","婴儿","宝宝","小孩","幼儿"],
            [
                cat("kids_baby", "婴儿服装", ["baby clothes","infant wear","newborn","婴儿衣服","新生儿"], [
                    cat("kids_baby_romper","婴儿连体衣",["baby romper","baby onesie","婴儿连体衣"]),
                    cat("kids_baby_set","婴儿套装",["baby set","baby outfit","婴儿套装"]),
                ]),
                cat("kids_girl", "女童服装", ["girls clothes","girl dress","female kids","女童","小女孩"], [
                    cat("kids_girl_dress","女童连衣裙",["girls dress","girl skirt","女童裙子","女童连衣裙"]),
                    cat("kids_girl_top","女童上衣",["girls top","girls shirt","女童上衣"]),
                    cat("kids_girl_pants","女童裤子",["girls pants","girls leggings","女童裤子"]),
                ]),
                cat("kids_boy", "男童服装", ["boys clothes","boy shirt","male kids","男童","小男孩"], [
                    cat("kids_boy_top","男童上衣",["boys top","boys tee","男童上衣","男童t恤"]),
                    cat("kids_boy_pants","男童裤子",["boys pants","boys shorts","男童裤子"]),
                    cat("kids_boy_jacket","男童外套",["boys jacket","boys coat","男童外套"]),
                ]),
            ]
        ),
        cat("shoes", "鞋靴",
            ["shoes","boots","sneakers","heels","sandals","slippers","loafers","flats","pumps","footwear","鞋","靴","凉鞋","运动鞋","高跟鞋","拖鞋","鞋靴"],
            [
                cat("shoes_sneakers", "运动鞋休闲鞋", ["sneakers","trainers","athletic shoes","运动鞋","休闲鞋"], [
                    cat("shoes_sneakers_running","跑步鞋",["running shoes","跑步鞋","跑鞋"]),
                    cat("shoes_sneakers_casual","休闲运动鞋",["casual sneakers","lifestyle sneakers","休闲运动鞋"]),
                ]),
                cat("shoes_heels", "高跟鞋", ["heels","high heels","pumps","stiletto","wedge heels","高跟鞋","坡跟鞋"], [
                    cat("shoes_heels_stiletto","细跟高跟鞋",["stiletto heels","spike heels","细跟鞋"]),
                    cat("shoes_heels_block","粗跟高跟鞋",["block heels","chunky heels","粗跟鞋"]),
                    cat("shoes_heels_wedge","坡跟鞋",["wedge shoes","wedge heels","坡跟鞋"]),
                    cat("shoes_heels_kitten","猫跟鞋",["kitten heels","低跟鞋"]),
                ]),
                cat("shoes_sandals", "凉鞋", ["sandals","flip flops","thong sandals","凉鞋","人字拖"], [
                    cat("shoes_sandals_flat","平底凉鞋",["flat sandals","平底凉鞋"]),
                    cat("shoes_sandals_heeled","高跟凉鞋",["heeled sandals","高跟凉鞋"]),
                    cat("shoes_sandals_flip","人字拖",["flip flops","thong sandals","人字拖"]),
                ]),
                cat("shoes_boots", "靴子", ["boots","ankle boots","knee boots","thigh boots","靴子","短靴","长靴"], [
                    cat("shoes_boots_ankle","短靴",["ankle boots","短靴"]),
                    cat("shoes_boots_knee","及膝靴",["knee boots","knee high boots","及膝靴"]),
                    cat("shoes_boots_thigh","过膝靴",["thigh boots","thigh high boots","过膝靴"]),
                ]),
                cat("shoes_flats", "平底鞋", ["flats","loafers","mules","ballet flats","平底鞋","乐福鞋","穆勒鞋"], [
                    cat("shoes_flats_loafer","乐福鞋",["loafers","乐福鞋"]),
                    cat("shoes_flats_ballet","芭蕾平底鞋",["ballet flats","芭蕾鞋","平底鞋"]),
                    cat("shoes_flats_mules","穆勒鞋",["mules","穆勒鞋","一脚蹬"]),
                ]),
                cat("shoes_slippers", "拖鞋", ["slippers","house shoes","slides","拖鞋","家居鞋"], [
                    cat("shoes_slippers_indoor","室内拖鞋",["indoor slippers","house slippers","室内拖鞋"]),
                    cat("shoes_slippers_outdoor","外穿拖鞋",["outdoor slippers","slides","外穿拖鞋"]),
                ]),
            ]
        ),
        cat("bags", "包袋",
            ["bag","handbag","backpack","purse","tote","clutch","wallet","包","钱包","背包","手提包","包袋"],
            [
                cat("bags_handbag", "手提包", ["handbag","top handle bag","手提包"], [
                    cat("bags_handbag_tote","托特包",["tote bag","托特包"]),
                    cat("bags_handbag_satchel","医生包",["satchel","doctor bag","医生包"]),
                    cat("bags_handbag_mini","迷你包",["mini bag","micro bag","迷你包"]),
                ]),
                cat("bags_shoulder", "单肩包", ["shoulder bag","crossbody bag","单肩包","斜挎包"], [
                    cat("bags_shoulder_crossbody","斜挎包",["crossbody bag","斜挎包","斜背包"]),
                    cat("bags_shoulder_hobo","水桶包",["hobo bag","bucket bag","水桶包"]),
                ]),
                cat("bags_backpack", "背包", ["backpack","rucksack","背包","双肩包"], [
                    cat("bags_backpack_casual","休闲背包",["casual backpack","休闲背包","双肩包"]),
                    cat("bags_backpack_mini","迷你背包",["mini backpack","迷你背包"]),
                ]),
                cat("bags_clutch", "手拿包", ["clutch","evening bag","envelope bag","手拿包","信封包"], [
                    cat("bags_clutch_evening","晚宴包",["evening clutch","晚宴包"]),
                    cat("bags_clutch_envelope","信封包",["envelope clutch","信封包"]),
                ]),
                cat("bags_wallet", "钱包", ["wallet","purse","card holder","钱包","卡包","零钱包"], [
                    cat("bags_wallet_long","长款钱包",["long wallet","长款钱包"]),
                    cat("bags_wallet_short","短款钱包",["short wallet","bifold wallet","短款钱包"]),
                    cat("bags_wallet_card","卡包",["card holder","card wallet","卡包"]),
                ]),
            ]
        ),
        cat("accessories", "配饰",
            ["necklace","bracelet","earring","ring","jewelry","watch","sunglasses","hat","scarf","belt","gloves","项链","手链","耳环","戒指","手表","太阳镜","帽子","围巾","腰带","配饰"],
            [
                cat("acc_jewelry", "珠宝首饰", ["jewelry","jewellery","珠宝","首饰"], [
                    cat("acc_jewelry_necklace","项链",["necklace","chain","pendant","项链","吊坠"]),
                    cat("acc_jewelry_bracelet","手链手镯",["bracelet","bangle","手链","手镯"]),
                    cat("acc_jewelry_earring","耳环",["earring","earrings","stud","hoop","耳环","耳钉","耳圈"]),
                    cat("acc_jewelry_ring","戒指",["ring","rings","戒指","指环"]),
                    cat("acc_jewelry_anklet","脚链",["anklet","ankle bracelet","脚链"]),
                ]),
                cat("acc_watch", "手表", ["watch","timepiece","手表","腕表"], [
                    cat("acc_watch_women","女表",["women watch","ladies watch","女表","女士手表"]),
                    cat("acc_watch_men","男表",["men watch","mens watch","男表","男士手表"]),
                ]),
                cat("acc_glasses", "眼镜", ["sunglasses","eyewear","glasses","太阳镜","墨镜","眼镜"], [
                    cat("acc_glasses_sun","太阳镜",["sunglasses","sun glasses","shades","太阳镜","墨镜"]),
                    cat("acc_glasses_reading","平光眼镜",["reading glasses","fashion glasses","平光眼镜"]),
                ]),
                cat("acc_hat", "帽子", ["hat","cap","beanie","beret","帽子","棒球帽","渔夫帽","贝雷帽"], [
                    cat("acc_hat_baseball","棒球帽",["baseball cap","snapback","棒球帽"]),
                    cat("acc_hat_bucket","渔夫帽",["bucket hat","fisherman hat","渔夫帽"]),
                    cat("acc_hat_beanie","毛线帽",["beanie","knit hat","毛线帽","针织帽"]),
                    cat("acc_hat_beret","贝雷帽",["beret","贝雷帽"]),
                    cat("acc_hat_straw","草帽",["straw hat","sun hat","草帽","遮阳帽"]),
                ]),
                cat("acc_scarf", "围巾", ["scarf","shawl","wrap","围巾","丝巾","披肩"], [
                    cat("acc_scarf_winter","冬季围巾",["winter scarf","wool scarf","冬季围巾","毛围巾"]),
                    cat("acc_scarf_silk","丝巾",["silk scarf","satin scarf","丝巾","真丝围巾"]),
                    cat("acc_scarf_shawl","披肩",["shawl","wrap scarf","披肩"]),
                ]),
                cat("acc_belt", "腰带", ["belt","waist belt","腰带","皮带","腰封"], [
                    cat("acc_belt_leather","皮带",["leather belt","皮带"]),
                    cat("acc_belt_waist","腰封",["waist belt","corset belt","腰封","宽腰带"]),
                ]),
                cat("acc_gloves", "手套", ["gloves","mittens","手套"], [
                    cat("acc_gloves_winter","冬季手套",["winter gloves","wool gloves","冬季手套","保暖手套"]),
                    cat("acc_gloves_touch","触屏手套",["touch screen gloves","触屏手套"]),
                ]),
            ]
        ),
        cat("sports", "运动户外",
            ["sport","gym","yoga","outdoor","fitness","athletic","running","hiking","cycling","workout","运动","健身","户外","瑜伽","跑步","骑行"],
            [
                cat("sports_yoga", "瑜伽服", ["yoga wear","yoga pants","yoga top","yoga set","瑜伽服","瑜伽裤"], [
                    cat("sports_yoga_pants","瑜伽裤",["yoga pants","瑜伽裤"]),
                    cat("sports_yoga_top","瑜伽上衣",["yoga top","sports bra","瑜伽上衣","运动内衣"]),
                    cat("sports_yoga_set","瑜伽套装",["yoga set","workout set","瑜伽套装","运动套装"]),
                ]),
                cat("sports_running", "跑步装备", ["running wear","running clothes","跑步服","跑步装备"], [
                    cat("sports_running_shirt","跑步上衣",["running shirt","running top","跑步上衣"]),
                    cat("sports_running_shorts","跑步短裤",["running shorts","跑步短裤"]),
                    cat("sports_running_jacket","运动外套",["running jacket","运动外套"]),
                ]),
                cat("sports_swim", "泳装", ["swimwear","swimsuit","bikini","swim","泳衣","泳装","比基尼"], [
                    cat("sports_swim_one","连体泳衣",["one piece swimsuit","swimsuit","连体泳衣"]),
                    cat("sports_swim_bikini","比基尼",["bikini","two piece swimsuit","比基尼"]),
                    cat("sports_swim_cover","泳装外搭",["swim cover up","sarong","泳装外搭","沙滩裙"]),
                ]),
                cat("sports_outdoor", "户外运动", ["outdoor wear","hiking","camping","户外服装","登山","徒步"], [
                    cat("sports_outdoor_jacket","冲锋衣",["hiking jacket","outdoor jacket","shell jacket","冲锋衣"]),
                    cat("sports_outdoor_pants","户外裤",["hiking pants","outdoor pants","户外裤","徒步裤"]),
                ]),
            ]
        ),
        cat("beauty", "美妆个护",
            ["makeup","skincare","beauty","lipstick","foundation","mascara","perfume","lotion","serum","shampoo","conditioner","美妆","护肤","口红","香水","洗发水"],
            [
                cat("beauty_makeup", "彩妆", ["makeup","cosmetics","彩妆","化妆品"], [
                    cat("beauty_makeup_lip","唇部彩妆",["lipstick","lip gloss","lip liner","口红","唇彩","唇釉"]),
                    cat("beauty_makeup_eye","眼部彩妆",["mascara","eyeliner","eyeshadow","睫毛膏","眼线笔","眼影"]),
                    cat("beauty_makeup_face","面部彩妆",["foundation","concealer","blush","highlighter","粉底","遮瑕","腮红","高光"]),
                    cat("beauty_makeup_nail","美甲",["nail polish","nail art","指甲油","美甲"]),
                ]),
                cat("beauty_skincare", "护肤", ["skincare","skin care","护肤品","护肤"], [
                    cat("beauty_skincare_moisturizer","保湿乳液",["moisturizer","lotion","cream","保湿霜","乳液","面霜"]),
                    cat("beauty_skincare_serum","精华",["serum","essence","精华液","精华"]),
                    cat("beauty_skincare_sunscreen","防晒",["sunscreen","sunblock","spf","防晒霜","防晒"]),
                    cat("beauty_skincare_mask","面膜",["face mask","sheet mask","面膜"]),
                ]),
                cat("beauty_fragrance", "香水", ["perfume","fragrance","cologne","香水","香氛"], [
                    cat("beauty_fragrance_women","女士香水",["women perfume","floral fragrance","女士香水"]),
                    cat("beauty_fragrance_men","男士香水",["men cologne","men perfume","男士香水"]),
                ]),
                cat("beauty_hair", "头发护理", ["shampoo","conditioner","hair care","hair mask","洗发水","护发素","发膜"], [
                    cat("beauty_hair_shampoo","洗发水",["shampoo","洗发水","洗发露"]),
                    cat("beauty_hair_conditioner","护发素",["conditioner","hair conditioner","护发素"]),
                    cat("beauty_hair_mask","发膜",["hair mask","发膜"]),
                ]),
            ]
        ),
        cat("home", "家居生活",
            ["home","kitchen","bedroom","pillow","blanket","curtain","towel","candle","lamp","furniture","decor","storage","家居","厨房","卧室","枕头","毯子","窗帘","毛巾","蜡烛","台灯"],
            [
                cat("home_bedding", "床上用品", ["bedding","pillow","blanket","duvet","sheet","床上用品","枕头","毯子","被子","床单"], [
                    cat("home_bedding_pillow","枕头枕套",["pillow","pillowcase","枕头","枕套"]),
                    cat("home_bedding_blanket","毯子被子",["blanket","duvet","comforter","毯子","被子"]),
                    cat("home_bedding_sheet","床单床笠",["bed sheet","fitted sheet","床单","床笠"]),
                ]),
                cat("home_decor", "家居装饰", ["home decor","decoration","candle","lamp","wall art","家居装饰","蜡烛","台灯","壁挂"], [
                    cat("home_decor_candle","蜡烛香薰",["candle","scented candle","蜡烛","香薰"]),
                    cat("home_decor_lamp","灯具",["lamp","night light","led light","台灯","小夜灯"]),
                    cat("home_decor_wallart","墙面装饰",["wall art","poster","wall decor","墙贴","装饰画"]),
                ]),
                cat("home_kitchen", "厨房用品", ["kitchen","cookware","bakeware","utensils","厨房","炊具","烘焙","厨具"], [
                    cat("home_kitchen_cookware","锅具",["pot","pan","cookware","锅","平底锅","汤锅"]),
                    cat("home_kitchen_storage","厨房收纳",["kitchen storage","food container","厨房收纳","保鲜盒"]),
                    cat("home_kitchen_tool","厨具工具",["kitchen tool","utensil","spatula","厨具","铲子","刀具"]),
                ]),
                cat("home_bath", "浴室用品", ["towel","bath","shower","bathroom","毛巾","浴室","卫浴"], [
                    cat("home_bath_towel","毛巾浴巾",["towel","bath towel","毛巾","浴巾"]),
                    cat("home_bath_accessory","浴室配件",["bath accessory","shower curtain","浴帘","浴室配件"]),
                ]),
                cat("home_storage", "收纳整理", ["storage","organizer","basket","box","收纳","整理","储物"], [
                    cat("home_storage_basket","收纳篮筐",["storage basket","wicker basket","收纳篮","收纳筐"]),
                    cat("home_storage_box","收纳盒",["storage box","organizer box","收纳盒","储物盒"]),
                ]),
            ]
        ),
        cat("electronics", "电子数码",
            ["phone","charger","cable","headphone","earphone","tablet","laptop","keyboard","mouse","electronic","digital","bluetooth","手机","充电","耳机","数码"],
            [
                cat("elec_phone_acc", "手机配件", ["phone case","screen protector","phone accessory","手机壳","钢化膜","手机配件"], [
                    cat("elec_phone_case","手机壳",["phone case","phone cover","手机壳","手机套"]),
                    cat("elec_phone_screen","贴膜",["screen protector","tempered glass","贴膜","钢化膜"]),
                ]),
                cat("elec_audio", "音频设备", ["headphone","earphone","earbuds","speaker","耳机","音响","扬声器"], [
                    cat("elec_audio_headphone","头戴耳机",["headphone","over ear headphones","头戴耳机"]),
                    cat("elec_audio_earbuds","无线耳机",["earbuds","wireless earphones","tws","无线耳机","蓝牙耳机"]),
                    cat("elec_audio_speaker","蓝牙音响",["bluetooth speaker","portable speaker","蓝牙音响","便携音响"]),
                ]),
                cat("elec_charging", "充电设备", ["charger","cable","power bank","charging","充电器","数据线","充电宝"], [
                    cat("elec_charging_charger","充电器",["charger","wall charger","usb charger","充电器","充电头"]),
                    cat("elec_charging_cable","数据线",["usb cable","charging cable","数据线","充电线"]),
                    cat("elec_charging_powerbank","充电宝",["power bank","portable charger","充电宝"]),
                ]),
                cat("elec_computer", "电脑配件", ["keyboard","mouse","laptop stand","webcam","键盘","鼠标","笔记本支架"], [
                    cat("elec_computer_keyboard","键盘",["keyboard","mechanical keyboard","键盘","机械键盘"]),
                    cat("elec_computer_mouse","鼠标",["mouse","wireless mouse","鼠标","无线鼠标"]),
                ]),
            ]
        ),
        cat("pet", "宠物用品",
            ["pet","dog","cat","collar","leash","pet toy","pet food","宠物","狗","猫","宠物用品"],
            [
                cat("pet_dog", "狗狗用品", ["dog","puppy","狗","狗狗","幼犬"], [
                    cat("pet_dog_collar","狗项圈牵引绳",["dog collar","dog leash","dog harness","狗项圈","牵引绳"]),
                    cat("pet_dog_toy","狗玩具",["dog toy","chew toy","狗玩具","宠物玩具"]),
                    cat("pet_dog_clothes","宠物衣服",["dog clothes","pet clothes","狗衣服","宠物衣服"]),
                ]),
                cat("pet_cat", "猫咪用品", ["cat","kitten","猫","猫咪","幼猫"], [
                    cat("pet_cat_toy","猫玩具",["cat toy","cat wand","逗猫棒","猫玩具"]),
                    cat("pet_cat_bed","猫窝猫床",["cat bed","cat house","猫窝","猫床"]),
                ]),
            ]
        ),
    ]
}

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shein_categories.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("Written to:", path)
print("Top-level categories:", [c["name"] for c in data["categories"]])

                    