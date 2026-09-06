#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
cron: 5 11 * * *
new Env('数码之家自动签到')
"""

import os
import re
import random
import time
import hashlib
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------- 统一通知模块加载 ----------------
hadsend = False
send = None
try:
    from notify import send
    hadsend = True
    print("✅ 已加载notify.py通知模块")
except ImportError:
    print("⚠️  未加载通知模块，跳过通知功能")

# ---------------- 站点配置 ----------------
BASE_URL = "https://www.mydigit.cn"
PORTAL = f"{BASE_URL}/"
SIGN_PAGE = f"{BASE_URL}/k_misign-sign.html"
LOGIN_PAGE = f"{BASE_URL}/member.php?mod=logging&action=login&handlekey=login"

# ---------------- 配置项（环境变量） ----------------
max_random_delay = int(os.getenv("MAX_RANDOM_DELAY", "3600"))  # 随机延迟最大秒数，0表示关闭随机延迟
privacy_mode = os.getenv("PRIVACY_MODE", "true").lower() == "true"  # 隐私模式
question_id = os.getenv("QUESTION_ID", "0")  # 安全问题ID，0为不使用
answer = os.getenv("ANSWER", "")  # 安全问题答案


def mask_sensitive_data(data):
    """脱敏处理敏感数据"""
    if not data:
        return "未知"
    if len(data) <= 4:
        return "*" * len(data)
    return f"{data[:2]}...{data[-2:]}"


def generate_account_id(username):
    """生成账号唯一标识（用于区分多账号，不暴露真实信息）"""
    if not username:
        return "未知账号"
    hash_obj = hashlib.md5(username.encode())
    return f"账号{hash_obj.hexdigest()[:8].upper()}"


def notify_user(title, content):
    """统一通知函数"""
    if hadsend:
        try:
            send(title, content)
            print(f"✅ 通知发送完成: {title}")
        except Exception as e:
            print(f"❌ 通知发送失败: {e}")
    else:
        print(f"📢 {title}\n📄 {content}")


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


def parse_sign_response(response_text):
    """从签到响应内容中提取实际结果"""
    m = re.search(r'<!\[CDATA\[(.*?)\]\]>', response_text)
    if m:
        return m.group(1)
    return None


class MyDigit:
    name = "数码之家"

    def __init__(self, username: str, password: str, index: int = 1):
        self.username = username.strip()
        self.password = password.strip()
        self.index = index
        self.account_id = generate_account_id(self.username)
        self.session = None

    def _init_session(self):
        """初始化新 session"""
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36",
            "Host": "www.mydigit.cn",
            "Referer": PORTAL,
        })
        self.session = session

    def _visit_homepage(self):
        """Step 1: 请求首页"""
        print("🌐 请求首页...")
        r = self.session.get(PORTAL, timeout=15)
        r.raise_for_status()

    def _get_login_form(self):
        """Step 3: 请求登录弹窗页面，获取 loginhash 和 formhash"""
        print("🔑 请求登录弹窗页面获取 loginhash 和 formhash...")
        url = f"{LOGIN_PAGE}&infloat=yes&inajax=1&ajaxtarget=fwin_content_login"
        r = self.session.get(url, timeout=15)
        r.raise_for_status()
        return r.text

    def _do_login(self, loginhash, formhash):
        """Step 4: 提交登录"""
        print("🔄 开始提交登录请求...")
        login_url = f"{LOGIN_PAGE}&loginsubmit=yes&loginhash={loginhash}&inajax=1"
        payload = {
            "formhash": formhash,
            "referer": PORTAL,
            "username": self.username,
            "password": self.password,
            "questionid": question_id,
            "answer": answer,
        }
        r = self.session.post(login_url, data=payload, timeout=15)
        r.raise_for_status()
        return r.text

    def login(self):
        """执行完整登录流程，返回 (是否成功, 错误信息)"""
        try:
            print("🌐 开始新的登录流程...")
            self._init_session()

            # Step 1: 首页
            self._visit_homepage()
            time.sleep(1)

            # Step 2: 登录弹窗，获取 loginhash, formhash
            html1 = self._get_login_form()
            loginhash = get_loginhash(html1)
            formhash = get_formhash(html1)
            print(f"🔍 loginhash: {loginhash}, formhash: {formhash}")

            if not formhash:
                return False, "未能获取登录表单，请稍后重试"

            # Step 3: 登录
            login_resp = self._do_login(loginhash, formhash)
            print("✅ 登录操作已完成")

            # 简单校验是否登录成功（扫码/密码错误情况）
            if "登录失败" in login_resp or "密码错误" in login_resp or "用户名或密码" in login_resp:
                return False, "用户名或密码错误，请检查"

            time.sleep(5) # delay_time 硬编延迟5秒
            return True, None

        except requests.exceptions.Timeout:
            return False, "登录请求超时，网络连接可能有问题"
        except requests.exceptions.ConnectionError:
            return False, "网络连接错误，无法连接到数码之家服务器"
        except Exception as e:
            return False, f"登录异常: {str(e)}"

    def sign(self):
        """执行签到（需先登录成功）"""
        try:
            print("📝 正在执行签到...")

            # Step 1: 进入签到页获取新 formhash
            print("🔍 请求签到页面...")
            r = self.session.get(SIGN_PAGE, timeout=15)
            r.raise_for_status()
            formhash = get_formhash(r.text)
            print(f"🔍 签到页面 formhash: {formhash}")

            if not formhash:
                return "未获取到签到 formhash，可能登录已失效", False, ""

            # Step 2: 签到
            sign_url = f"{BASE_URL}/plugin.php?id=k_misign:sign&operation=qiandao&formhash={formhash}&format=empty"
            print(f"🔗 签到地址: {sign_url}")
            r = self.session.get(sign_url, timeout=15)
            r.raise_for_status()

            result = parse_sign_response(r.text)
            if result is None:
                print("❌ 签到响应解析失败，原始响应：")
                print(r.text[:500])
                return "签到响应解析失败，可能已签到或登录失效", False, ""

            print(f"🎉 {result}")
            if "失败" in result:
                return f"签到未成功：{result}", False, result
            else:
                return f"签到成功：{result}", True, result

        except requests.exceptions.Timeout:
            return "签到请求超时，网络连接可能有问题", False, ""
        except requests.exceptions.ConnectionError:
            return "网络连接错误，无法连接到数码之家服务器", False, ""
        except Exception as e:
            return f"签到异常: {str(e)}", False, ""

    def main(self):
        """主执行函数"""
        print(f"\n==== 账号{self.index} 开始签到 ====")

        if privacy_mode:
            print(f"👤 用户名: {mask_sensitive_data(self.username)}")
        else:
            print(f"👤 用户名: {self.username}")

        # 1. 登录
        login_ok, login_err = self.login()
        if not login_ok:
            full_error_msg = f"""登录失败

❌ 错误原因: {login_err}

🔧 解决方法:
1. 确认 MYDIGIT_ACCOUNT 中用户名密码是否正确
2. 若账号设置了安全问题，请同时配置 QUESTION_ID 和 ANSWER 环境变量
3. 检查网络是否可访问数码之家"""
            print(f"❌ {full_error_msg}")
            return full_error_msg, False

        # 2. 签到
        sign_msg, is_success, result = self.sign()

        # 3. 组合结果消息（通知用）
        final_msg = f"""🌟 数码之家签到结果

👤 账号: {self.account_id}"""

        final_msg += f"""
📝 签到: {sign_msg}"""

        final_msg += f"\n⏰ 时间: {datetime.now().strftime('%m-%d %H:%M')}"

        print(f"{'✅ 签到成功' if is_success else '❌ 签到失败'}")
        return final_msg, is_success


def run_account_task(username, password, index):
    """并发执行的单个账号任务，执行前按随机延迟错峰"""
    account_id = generate_account_id(username)
    try:
        # 每个账号独立随机延迟（错峰签到，避免并发同时请求被风控），MAX_RANDOM_DELAY=0 则关闭
        delay = random.uniform(0, max_random_delay) if max_random_delay > 0 else 0
        if delay > 0:
            print(f"账号{index} 随机延迟: {delay:.1f}秒")
            time.sleep(delay)

        # 执行登录并签到
        mydigit = MyDigit(username, password, index)
        result_msg, is_success = mydigit.main()
        return {
            'index': index,
            'success': is_success,
            'message': result_msg,
            'account_id': mydigit.account_id
        }
    except Exception as e:
        error_msg = f"账号{index}: 执行异常 - {str(e)}"
        print(f"❌ {error_msg}")
        return {
            'index': index,
            'success': False,
            'message': error_msg,
            'account_id': account_id
        }


def main():
    """主程序入口"""
    print(f"==== 数码之家自动签到开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")

    # 显示配置状态
    print(f"🔒 隐私保护模式: {'已启用' if privacy_mode else '已禁用'}")
    print(f"🔑 安全问题: {'已配置' if question_id != '0' else '未使用'}")

    # 获取账号配置
    accounts = os.getenv("MYDIGIT_ACCOUNT", "")

    if not accounts:
        error_msg = """❌ 未找到MYDIGIT_ACCOUNT环境变量

🔧 环境变量配置方法:
1. 在青龙面板添加环境变量 MYDIGIT_ACCOUNT
2. 值格式: 每行一个账号,「用户名 密码」用空格分隔
3. 支持多账号，多个账号用换行分隔

📝 示例:
    user1 pass1
    user2 pass2

💡 若账号设置了登录安全问题:
   另配置 QUESTION_ID(问题ID) 和 ANSWER(答案) 环境变量"""
        print(error_msg)
        notify_user("数码之家签到失败", error_msg)
        return

    # 解析账号（每行「用户名 密码」，空格分隔，换行分隔多账号）
    account_list = []
    for line in accounts.replace('\r\n', '\n').split('\n'):
        parts = line.strip().split()
        if len(parts) >= 2:
            account_list.append((parts[0], parts[1]))
        elif len(parts) == 1:
            print(f"⚠️  账号行格式错误（需「用户名 密码」）: {parts[0]}")

    if not account_list:
        print("❌ 未解析到有效账号，请检查 MYDIGIT_ACCOUNT 格式。每行应为「用户名 密码」")
        notify_user("数码之家签到失败", "MYDIGIT_ACCOUNT 格式错误，请检查「用户名 密码」格式")
        return

    print(f"📝 共发现 {len(account_list)} 个账号")

    total_count = len(account_list)
    # 不限制并发数，每个账号一个线程独立执行
    max_workers = total_count
    print(f"🚀 并行执行，所有账号同时运行，共 {max_workers} 个账号")

    # 并发执行所有账号签到
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(run_account_task, username, password, index + 1): index + 1
            for index, (username, password) in enumerate(account_list)
        }
        for future in as_completed(future_map):
            results.append(future.result())

    # 按账号顺序排序，便于汇总展示
    results.sort(key=lambda r: r['index'])

    success_count = sum(1 for r in results if r['success'])

    # 发送单个账号通知
    for result in results:
        status = "成功" if result['success'] else "失败"
        title = f"数码之家账号{result['index']}签到{status}"
        notify_user(title, result['message'])

    # 发送汇总通知
    if total_count > 1:
        summary_msg = f"""📊 数码之家签到汇总

📈 总计: {total_count}个账号
✅ 成功: {success_count}个
❌ 失败: {total_count - success_count}个
📊 成功率: {success_count/total_count*100:.1f}%
⏰ 完成时间: {datetime.now().strftime('%m-%d %H:%M')}"""

        # 添加详细结果
        if len(results) <= 5:
            summary_msg += "\n\n📋 详细结果:"
            for result in results:
                status_icon = "✅" if result['success'] else "❌"
                summary_msg += f"\n{status_icon} 账号{result['index']}"

        notify_user("数码之家签到汇总", summary_msg)

    print(f"\n==== 数码之家自动签到完成 - 成功{success_count}/{total_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")


if __name__ == "__main__":
    main()