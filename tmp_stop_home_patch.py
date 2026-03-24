# -*- coding: utf-8 -*-
import io

path = r'd:\Work\Project\Python\Shein上品软件\shein_upload.py'
with io.open(path, 'r', encoding='utf-8') as f:
    txt = f.read()

old = '''            def _force_stop_if_needed():
                time.sleep(3)
                if self._publish_running:
                    try:
                        if self._shein_publisher is not None and self._shein_publisher.is_alive():
                            self._pub_log("[STOP] 检测到后台仍在执行，强制关闭当前浏览器会话")
                            self._shein_publisher.quit()
                    except Exception:
                        pass
                    self._shein_publisher = None
                    self.after(0, lambda: self.status_lbl.config(text="已强制停止上品（浏览器会话已关闭）"))

            threading.Thread(target=_force_stop_if_needed, daemon=True).start()'''

new = '''            def _go_home_after_stop():
                time.sleep(1.5)
                try:
                    if self._shein_publisher is not None and self._shein_publisher.is_alive():
                        self._pub_log("[STOP] 停止后返回主页...")
                        self._shein_publisher.driver.get("https://www.geiwohuo.com/#/oversea-home")
                        self.after(0, lambda: self.status_lbl.config(text="已停止上品，已返回主页"))
                except Exception as e:
                    self._pub_log("[STOP] 返回主页失败: {}".format(str(e)[:60]))

            threading.Thread(target=_go_home_after_stop, daemon=True).start()'''

if old in txt:
    txt = txt.replace(old, new, 1)

# 更新提示文案
txt = txt.replace("若3秒后后台仍在执行，将自动强制中断当前浏览器会话。", "停止后浏览器将自动返回主页。")

with io.open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(txt)

print('patched')
