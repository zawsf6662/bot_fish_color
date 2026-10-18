import cv2
import numpy as np
import win32gui, win32ui, win32con, win32api
import ctypes
import time
from threading import Thread
from pynput import mouse
import pyautogui

user32 = ctypes.windll.user32

class SeniorHighFreqBot:
    def __init__(self, window_title="Roblox"):
        self.hwnd = win32gui.FindWindow(None, window_title)
        if not self.hwnd:
            print(f"❌ Error: ไม่พบหน้าต่าง {window_title}")
            exit()
            
        self.roi_x, self.roi_y = 0, 0
        self.roi_size = 150
        self.display_frame = None
        self.running = True
        
        # --- State Control ---
        self.state = "INIT" 
        self.last_state_change = 0
        self.stable_since = 0
        self.last_y = None
        self.anchor_pos = (0, 0)
        self.win_name = "Bot_Monitor (Q to Exit)"

    def send_background_click(self):
        """ส่งคลิกซ้ายแบบ Force Background Click (ใช้สำหรับ Cast)"""
        if not self.hwnd: return
        
        point = win32gui.ScreenToClient(self.hwnd, (self.abs_x, self.abs_y))
        lparam = win32api.MAKELONG(point[0], point[1])
        
        print(f"🖱️ Background Click at: {point}")
        win32gui.PostMessage(self.hwnd, win32con.WM_ACTIVATE, win32con.WA_CLICKACTIVE, 0)
        win32gui.PostMessage(self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
        time.sleep(0.15) 
        win32gui.PostMessage(self.hwnd, win32con.WM_LBUTTONUP, 0, lparam)

    def capture_roi(self):
        try:
            left, top, right, bot = win32gui.GetWindowRect(self.hwnd)
            w, h = right - left, bot - top
            hwndDC = win32gui.GetWindowDC(self.hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
            saveDC.SelectObject(saveBitMap)
            user32.PrintWindow(self.hwnd, saveDC.GetSafeHdc(), 2)
            
            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)
            img = np.frombuffer(bmpstr, dtype='uint8').reshape((bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4))

            p = win32gui.ScreenToClient(self.hwnd, (self.abs_x, self.abs_y))
            rx, ry = p[0], p[1]

            y1, y2 = max(0, ry - self.roi_size//2), min(h, ry + self.roi_size//2)
            x1, x2 = max(0, rx - self.roi_size//2), min(w, rx + self.roi_size//2)
            
            roi = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGRA2BGR)
            
            win32gui.DeleteObject(saveBitMap.GetHandle())
            saveDC.DeleteDC()
            mfcDC.DeleteDC()
            win32gui.ReleaseDC(self.hwnd, hwndDC)
            return roi
        except Exception as e:
            print(f"Capture Error: {e}")
            return None

    def get_mask(self, hsv, lower, upper):
        mask = cv2.inRange(hsv, lower, upper)
        mask = cv2.dilate(mask, np.ones((3,3), np.uint8), iterations=1)
        return mask

    def worker(self):
        print("🚀 Worker Thread Started")
        while self.running:
            now = time.time()
            roi = self.capture_roi()
            if roi is None: continue

            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            
            # --- ทุ่นสีแดง/ชมพู ---
            red_mask = cv2.add(
                self.get_mask(hsv, np.array([0, 140, 20]), np.array([10, 255, 255])),
                self.get_mask(hsv, np.array([160, 140, 20]), np.array([180, 255, 255]))
            )
            
            contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            curr_pos = None
            if contours:
                c = max(contours, key=cv2.contourArea)
                if cv2.contourArea(c) > 5:
                    M = cv2.moments(c)
                    if M["m00"] != 0:
                        cx = int(M["m10"]/M["m00"])
                        cy = int(M["m01"]/M["m00"])
                        curr_pos = (cx, cy)
                        cv2.circle(roi, curr_pos, 5, (0, 255, 0), -1)

            # --- State Machine ---
            if self.state == "INIT":
                print("🎣 Casting...")
                self.send_background_click()
                self.state = "CASTING"
                self.last_state_change = now

            elif self.state == "CASTING":
                if now - self.last_state_change > 4.0:
                    self.state = "STABILIZING"
                    self.stable_since = 0

            elif self.state == "STABILIZING":
                if curr_pos:
                    if self.stable_since == 0: self.stable_since = now
                    if now - self.stable_since > 0.5:
                        self.anchor_pos = curr_pos
                        self.state = "MONITORING"
                        print(f"🔒 Locked Anchor at: {self.anchor_pos}")
                else: 
                    self.stable_since = 0

            elif self.state == "MONITORING":
                target_x, target_y = self.anchor_pos
                
                # วาดโซนตรวจจับ
                cv2.circle(roi, (target_x, target_y), 4, (0, 165, 255), -1)
                cv2.circle(roi, (target_x, target_y), 15, (0, 165, 255), 1)
                cv2.putText(roi, "LOCKED", (target_x - 20, target_y - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 165, 255), 1)
                
                # สแกนหาออร่าสีฟ้า (Cyan Aura)
                cyan_mask = self.get_mask(hsv, np.array([85, 100, 50]), np.array([105, 255, 200]))
                cyan_contours, _ = cv2.findContours(cyan_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for cc in cyan_contours:
                    if cv2.contourArea(cc) > 10:
                        M_C = cv2.moments(cc)
                        if M_C["m00"] != 0:
                            cx = int(M_C["m10"]/M_C["m00"])
                            cy = int(M_C["m01"]/M_C["m00"])
                            
                            dist = np.sqrt((cx - target_x)**2 + (cy - target_y)**2)
                            cv2.line(roi, (target_x, target_y), (cx, cy), (255, 255, 0), 1)

                            if dist < 15:
                                print(f"🎣 BITE! Aura hit Anchor (Dist: {dist:.1f})")
                                pyautogui.click(self.abs_x, self.abs_y)
                                self.state = "REELING"
                                self.last_state_change = now
                                break

            elif self.state == "REELING":
                if now - self.last_state_change > 3.0:
                    self.state = "INIT"

            self.display_frame = roi

    def start(self):
        print("📍 คลิกซ้ายที่ตำแหน่งทุ่น 1 ครั้งเพื่อเริ่ม...")
        with mouse.Listener(on_click=self._on_click) as listener:
            listener.join()

        cv2.namedWindow(self.win_name, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(self.win_name, cv2.WND_PROP_TOPMOST, 1)
        cv2.resizeWindow(self.win_name, 180, 180)

        Thread(target=self.worker, daemon=True).start()

        while self.running:
            if self.display_frame is not None:
                cv2.imshow(self.win_name, self.display_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.running = False; break
        cv2.destroyAllWindows()

    def _on_click(self, x, y, button, pressed):
        if pressed:
            self.abs_x, self.abs_y = x, y
            print(f"✅ Target set at: {x}, {y}")
            return False

if __name__ == "__main__":
    SeniorHighFreqBot("Roblox").start()
