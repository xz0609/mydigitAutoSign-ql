import requests
from urllib.parse import quote_plus
import time
import re
from datetime import datetime


def log(msg):
    print(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {msg}')


# ====== 配置信息（请填好自己的） ======
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36"
DELAY_TIME = 5  # 秒
USERNAME = ""  # 你的用户名
PASSWORD = ""  # 你的密码
QUESTION_ID = "0"
ANSWER = ""

# BASE 配置
BASE_URL = "https://www.mydigit.cn"
PORTAL = f"{BASE_URL}/"
SIGN_PAGE = f"{BASE_URL}/k_misign-sign.html"
LOGIN_PAGE = f"{BASE_URL}/member.php?mod=logging&action=login&handlekey=login"

# ====== Session 初始化 ======
session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Host": "www.mydigit.cn",
    "Referer": PORTAL,
})


def get_formhash(html):
    """从 HTML 中提取 formhash"""
    m = re.search(r'name=["\']formhash["\'] value=["\'](\w{8})["\']', html)
    if m:
        return m.group(1)
    return None


def get_loginhash(html):
    """从 HTML 中提取 loginhash"""
    m = re.search(r'loginhash=([a-zA-Z0-9]{5})', html)
    if m:
        return m.group(1)
    return None


def visit_homepage():
    log("请求首页...")
    r = session.get(PORTAL)
    r.raise_for_status()
    # 解析 lastact 时间，参考 shell 实现，但通常实际应用很少用，可略。


def sendmail(lastact=""):
    log("尝试 sendmail ...")
    url = f"{BASE_URL}/home.php?mod=misc&ac=sendmail&rand={lastact}"
    r = session.get(url, allow_redirects=True)
    r.raise_for_status()


def get_login_form():
    log("请求登录弹窗页面获取 loginhash 和 formhash ...")
    url = f"{LOGIN_PAGE}&infloat=yes&inajax=1&ajaxtarget=fwin_content_login"
    r = session.get(url)
    r.raise_for_status()
    return r.text


def do_login(loginhash, formhash):
    log("开始提交登录请求 ...")
    login_url = f"{LOGIN_PAGE}&loginsubmit=yes&loginhash={loginhash}&inajax=1"
    payload = {
        "formhash": formhash,
        "referer": PORTAL,
        "username": USERNAME,
        "password": PASSWORD,
        "questionid": QUESTION_ID,
        "answer": ANSWER
    }
    r = session.post(login_url, data=payload)
    r.raise_for_status()
    return r.text


def get_sign_page():
    log("请求签到页面，准备获取新 formhash ...")
    r = session.get(SIGN_PAGE)
    r.raise_for_status()
    return r.text


def do_sign(formhash):
    log("准备发送签到请求 ...")
    sign_url = f"{BASE_URL}/plugin.php?id=k_misign:sign&operation=qiandao&formhash={formhash}&format=empty"
    log(f"签到请求地址：{sign_url}")
    r = session.get(sign_url)
    log("签到请求响应如下：")
    print(r.text)
    r.raise_for_status()
    parse_sign_response(r.text)

def parse_sign_response(response_text):
    """
    从签到响应内容中提取实际结果
    """
    import re
    m = re.search(r'<!\[CDATA\[(.*?)\]\]>', response_text)
    if m:
        result = m.group(1)
        log(f"签到结果解析：{result}")
        return result
    else:
        log("签到结果解析失败，原始响应：")
        print(response_text)
        return None

def main():
    log("===== Python数码之家自动签到 开始 =====")
    # Step 1: 首页
    visit_homepage()
    # Step 2: sendmail (可选)
    sendmail()
    time.sleep(1)
    # Step 3: 登录弹窗，获取 loginhash, formhash
    html1 = get_login_form()
    loginhash = get_loginhash(html1)
    formhash = get_formhash(html1)
    log(f"loginhash: {loginhash}, formhash: {formhash}")
    # Step 4: 登录
    do_login(loginhash, formhash)
    log("登录操作已完成")
    time.sleep(DELAY_TIME)
    # Step 5: 进入签到页获取新 formhash
    html2 = get_sign_page()
    formhash2 = get_formhash(html2)
    log(f"签到页面的 formhash：{formhash2}")
    # Step 6: 签到
    do_sign(formhash2)
    log("===== Python数码之家自动签到 结束 =====")


if __name__ == "__main__":
    if USERNAME == "" or PASSWORD == "":
        log("请在脚本中填写你的用户名和密码后再运行！")
    else:
        main()