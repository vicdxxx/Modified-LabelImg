import pypinyin
from Pinyin2Hanzi import DefaultDagParams
from Pinyin2Hanzi import dag
all_list = ['gu','qiao','qian','qve','ge','gang','ga','lian','liao','rou','zong',\
    'tu','seng','yve','ti','te','jve','ta','nong','zhang','fan','ma','gua','die','gui',\
    'guo','gun','sang','diu','zi','ze','za','chen','zu','ba','dian','diao','nei','suo',\
    'sun','zhao','sui','kuo','kun','kui','cao','zuan','kua','den','lei','neng','men',\
    'mei','tiao','geng','chang','cha','che','fen','chi','fei','chu','shui','me','tuan',\
    'mo','mi','mu','dei','cai','zhan','zhai','can','ning','wang','pie','beng','zhuang',\
    'tan','tao','tai','song','ping','hou','cuan','lan','lao','fu','fa','jiong','mai',\
    'xiang','mao','man','a','jiang','zun','bing','su','si','sa','se','ding','xuan',\
    'zei','zen','kong','pang','jie','jia','jin','lo','lai','li','peng','jiu','yi','yo',\
    'ya','cen','dan','dao','ye','dai','zhen','bang','nou','yu','weng','en','ei','kang',\
    'dia','er','ru','keng','re','ren','gou','ri','tian','qi','shua','shun','shuo','qun',\
    'yun','xun','fiao','zan','zao','rang','xi','yong','zai','guan','guai','dong','kuai',\
    'ying','kuan','xu','xia','xie','yin','rong','xin','tou','nian','niao','xiu','fo',\
    'kou','niang','hua','hun','huo','hui','shuan','quan','shuai','chong','bei','ben',\
    'kuang','dang','sai','ang','sao','san','reng','ran','rao','ming','tei','lie','lia',\
    'min','pa','lin','mian','mie','liu','zou','miu','nen','kai','kao','kan','ka','ke',\
    'yang','ku','deng','dou','shou','chuang','nang','feng','meng','cheng','di','de','da',\
    'bao','gei','du','gen','qu','shu','sha','she','ban','shi','bai','nun','nuo','sen','lve',\
    'kei','fang','teng','xve','lun','luo','ken','wa','wo','ju','tui','wu','le','ji','huang',\
    'tuo','cou','la','mang','ci','tun','tong','ca','pou','ce','gong','cu','lv','dun','pu',\
    'ting','qie','yao','lu','pi','po','suan','chua','chun','chan','chui','gao','gan','zeng',\
    'gai','xiong','tang','pian','piao','cang','heng','xian','xiao','bian','biao','zhua','duan',\
    'cong','zhui','zhuo','zhun','hong','shuang','juan','zhei','pai','shai','shan','shao','pan',\
    'pao','nin','hang','nie','zhuai','zhuan','yuan','niu','na','miao','guang','ne','hai','han',\
    'hao','wei','wen','ruan','cuo','cun','cui','bin','bie','mou','nve','shen','shei','fou','xing',\
    'qiang','nuan','pen','pei','rui','run','ruo','sheng','dui','bo','bi','bu','chuan','qing',\
    'chuai','duo','o','chou','ou','zui','luan','zuo','jian','jiao','sou','wan','jing','qiong',\
    'wai','long','yan','liang','lou','huan','hen','hei','huai','shang','jun','hu','ling','ha','he',\
    'zhu','ceng','zha','zhe','zhi','qin','pin','ai','chai','qia','chao','ao','an','qiu','ni','zhong',\
    'zang','nai','nan','nao','chuo','tie','you','nu','nv','zheng','leng','zhou','lang','e','jue','xue',\
    'yue','eng','lue','nue','que','rua']
__removetone_dict = {
    'ā': 'a',
    'á': 'a',
    'ǎ': 'a',
    'à': 'a',
    'ē': 'e',
    'é': 'e',
    'ě': 'e',
    'è': 'e',
    'ī': 'i',
    'í': 'i',
    'ǐ': 'i',
    'ì': 'i',
    'ō': 'o',
    'ó': 'o',
    'ǒ': 'o',
    'ò': 'o',
    'ū': 'u',
    'ú': 'u',
    'ǔ': 'u',
    'ù': 'u',
    'ü': 'v',
    'ǖ': 'v',
    'ǘ': 'v',
    'ǚ': 'v',
    'ǜ': 'v',
    'ń': 'n',
    'ň': 'n',
    '': 'm',
}
__pinyin = set(all_list)

def all_pinyin():
    for _ in __pinyin:
        yield _

def remove_tone(one_py):
    """ 删除拼音中的音调
    lǔ -> lu
    """
    one_py = as_text(one_py)
    r = as_text('')
    for c in one_py:
        if c in __removetone_dict:
            r += __removetone_dict[c]
        else:
            r += c
    return r

def as_text(v):  ## 生成unicode字符串
    if v is None:
        return None
    elif isinstance(v, bytes):
        return v.decode('utf-8', errors='ignore')
    elif isinstance(v, str):
        return v
    else:
        raise ValueError('Unknown type %r' % type(v))
        
def py_result(result_list):
    for item in range(0,len(result_list)):
        item_list = list(result_list[item])
        num_list, res_list, num = [], [], 0
        for i in range(0, len(item_list)):
            one_py = item_list[i]
            num_list.append(one_py in __removetone_dict)
            if one_py in __removetone_dict:
                res_list.append("%s、" % one_py)
                num += 1
            else:
                res_list.append("%s" % one_py)
        if num > 1:
            py_ok = ' '.join(''.join(res_list).split("、")[:-2])
            py_end_ok = ''.join(''.join(res_list).split("、")[-2:])
            py_res = "%s %s"%(py_ok, py_end_ok)
            result_list[item] = py_res

def get_split_py(text):
    result_list = []
    py_text = remove_tone(text)

    def get_py(y):
        py_list = []
        for i in range(y, len(py_text) + 1):
            if y == 1:
                y = y - 1
            nr = py_text[y:i]
            y_nr = text[y:i]
            if nr in all_pinyin():
                py_list.append([y_nr,y,i])
        if py_list:
            result = py_list[-1][0]
            if py_list[-1][2] < len(text):
                nr = py_text[py_list[-1][2]-1:py_list[-1][2]+1]
                anr = py_text[py_list[-1][2]:py_list[-1][2]+2]
                if nr in all_pinyin() and anr not in all_pinyin():
                    result = py_list[-2][0]
        else:
            result=""
        return result

    py_str = get_py(1)
    while 1:
        result_list.append(py_str)
        num = len(''.join(result_list))
        if num < len(text):
            py_str = get_py(num)
        else:
            py_result(result_list)
            break
    return result_list

def chinese(pinyin):
    s = ''
    for i in pypinyin.pinyin(word, style=pypinyin.NORMAL):
       s += ''.join(i)
    return s

def pinyin(word):
    s = ''
    for i in pypinyin.pinyin(word, style=pypinyin.NORMAL):
       s += ''.join(i)
    return s
 
def pinyin_with_tone(word):
    s = ''
    # heteronym=True开启多音字
    for i in pypinyin.pinyin(word, heteronym=True):
       s = s + ''.join(i) + " "
    return s
 
def pinyin_2_chinese(text):
    result_list=get_split_py(text)

    dagParams = DefaultDagParams()
    result = dag(dagParams, result_list, path_num=10, log=True) #10代表侯选值个数
    #for item in result:
    #    score = item.score 
    #    res = item.path # 转换结果
    #    print(score, res)
    str=''
    for character in result[0].path:
        str+=character
    return str

def main():
    #print(pinyin("忠厚传家久"))
    #print(pinyin_with_tone("诗书继世长"))
    #pinyin_2_hanzi = ['jing', 'chang']
    #pinyin_2_hanzi(pinyin_2_hanzi)
    text="maidong"
    pinyin_2_chinese(text)

if __name__ == "__main__":
    main()