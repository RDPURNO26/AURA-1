# controller_process.py
"""
AURA v3 – Controller. Peace-sign move, drop-finger click.
Cursor only tracks when MOVE+peace or DRAGGING. Everything else = frozen.
"""
import logging, multiprocessing as mp, queue, time, math, ctypes
import numpy as np
from pathlib import Path

_log = logging.getLogger("aura.controller")

def _configure_file_logging():
    if logging.getLogger().handlers: return
    log_path = Path(__file__).resolve().parent / "aura.log"
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"),
                  logging.StreamHandler()], force=True)

class OneEuroFilter:
    def __init__(self, freq=60.0, fmin=1.5, beta=0.007, dcutoff=1.0):
        self.freq=freq; self.fmin=fmin; self.beta=beta; self.dcutoff=dcutoff
        self.x_prev=None; self.dx_prev=0.0; self.t_prev=None
    def reset(self, x, t=None):
        self.x_prev=float(x); self.dx_prev=0.0
        self.t_prev=t if t is not None else time.time()
    def _alpha(self, cutoff):
        te=1.0/max(self.freq,1); tau=1.0/(2*math.pi*cutoff)
        return 1.0/(1.0+tau/te)
    def __call__(self, x, t=None):
        if t is None: t=time.time()
        x=float(x)
        if self.x_prev is None:
            self.x_prev=x; self.t_prev=t; return x
        dt=t-self.t_prev
        if dt>1e-9: self.freq=min(120.0,max(25.0,1.0/dt))
        self.t_prev=t
        dx=(x-self.x_prev)*self.freq
        a_d=self._alpha(self.dcutoff)
        dx_hat=a_d*dx+(1-a_d)*self.dx_prev
        cutoff=self.fmin+self.beta*abs(dx_hat)
        a=self._alpha(cutoff)
        x_hat=a*x+(1-a)*self.x_prev
        self.x_prev=x_hat; self.dx_prev=dx_hat
        return x_hat

ZMX=0.10; ZMY=0.10; ANTI_TP=0.05

CONNECTIONS=[(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
    (0,9),(9,10),(10,11),(11,12),(0,13),(13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20),(5,9),(9,13),(13,17)]

STATE_COLORS={"IDLE":(120,120,120),"MOVE":(0,255,0),"CLICKING":(0,165,255),
    "DRAGGING":(0,0,255),"SCROLLING":(255,0,200),"ZOOMING":(200,0,255),
    "CLUTCH":(0,255,255),"VOLUME":(100,200,50)}

def get_virtual_screen_bounds():
    u=ctypes.windll.user32
    try: u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except: u.SetProcessDPIAware()
    vx=u.GetSystemMetrics(76); vy=u.GetSystemMetrics(77)
    vw=u.GetSystemMetrics(78); vh=u.GetSystemMetrics(79)
    if vw<=0 or vh<=0: vx,vy=0,0; vw=u.GetSystemMetrics(0); vh=u.GetSystemMetrics(1)
    return int(vx),int(vy),int(vw),int(vh)

def hand_to_norm(hx,hy):
    sx=1.0-2.0*ZMX; sy=1.0-2.0*ZMY
    if sx<=1e-6 or sy<=1e-6: return 0.5,0.5
    return max(0.0,min(1.0,(hx-ZMX)/sx)), max(0.0,min(1.0,(hy-ZMY)/sy))

def palm_to_screen(hx,hy,vx,vy,sw,sh):
    nx,ny=hand_to_norm(hx,hy)
    return vx+nx*max(sw-1,0), vy+ny*max(sh-1,0)

def _fext(lm,tip,pip,mcp,mc=0.42):
    t=lm[tip,:2].astype(np.float64); p=lm[pip,:2].astype(np.float64)
    m=lm[mcp,:2].astype(np.float64)
    v1=p-m; v2=t-p; n1=float(np.linalg.norm(v1)); n2=float(np.linalg.norm(v2))
    if n1<1e-5 or n2<1e-5: return False
    return float(np.dot(v1,v2)/(n1*n2))>=mc

def extract_inputs(lm, conf, prev_lm, dt=None):
    if dt is None or dt<=0: dt=1.0/30.0
    iu=_fext(lm,8,6,5); mu=_fext(lm,12,10,9)
    ru=_fext(lm,16,14,13); pu=_fext(lm,20,18,17)
    n=sum([iu,mu,ru,pu])

    # Thumb detection for double-click
    td=float(np.linalg.norm(lm[4,:2]-lm[5,:2]))
    ps=float(np.linalg.norm(lm[9,:2]-lm[0,:2]))
    thumb_out=(td/max(ps,1e-5))>0.55

    pcx=float(np.mean(lm[[5,9,13,17],0]))
    pcy=float(np.mean(lm[[5,9,13,17],1]))
    vv=0.0
    if prev_lm is not None:
        vv=(float(prev_lm[9,1])-float(lm[9,1]))/dt

    return dict(landmarks=lm, confidence=conf,
        is_peace=(iu and mu and not ru and not pu),
        is_fist=(n==0 and not thumb_out),
        is_thumb_only=(n==0 and thumb_out),
        is_index_only=(iu and not mu and not ru and not pu),
        is_middle_only=(mu and not iu and not ru and not pu),
        is_ring_only=(ru and not iu and not mu and not pu),
        is_three=(iu and mu and ru and not pu),
        is_four=(n>=4),
        is_pinky_only=(pu and not iu and not mu and not ru),
        is_dblclick=(iu and mu and thumb_out and not ru and not pu),
        hand_cx=pcx, hand_cy=pcy, vert_vel=vv)

def draw_overlay(frame,lm,state,action,conf,vx,vy,sw,sh,csx=None,csy=None):
    import cv2
    h,w=frame.shape[:2]; color=STATE_COLORS.get(state,(255,255,255))
    zx1=int(ZMX*w); zy1=int(ZMY*h); zx2=int((1-ZMX)*w); zy2=int((1-ZMY)*h)
    cv2.rectangle(frame,(zx1,zy1),(zx2,zy2),(0,255,0),1)
    if state=="CLUTCH":
        cv2.rectangle(frame,(0,0),(w-1,h-1),(255,255,0),3)
        cv2.putText(frame,"CLUTCH - recenter hand",(w//2-160,28),cv2.FONT_HERSHEY_SIMPLEX,0.55,(255,255,0),2)
    elif state=="LOCKED":
        cv2.rectangle(frame,(0,0),(w-1,h-1),(60,60,180),3)
        cv2.putText(frame,"LOCKED - peace sign to unlock",(w//2-200,28),cv2.FONT_HERSHEY_SIMPLEX,0.55,(180,180,255),2)
    if lm is not None:
        pts=[(int(lm[i,0]*w),int(lm[i,1]*h)) for i in range(21)]
        for a,b in CONNECTIONS: cv2.line(frame,pts[a],pts[b],(160,160,160),1)
        for i,pt in enumerate(pts):
            c=(0,255,0) if i in(5,9,13,17) else (255,255,255)
            cv2.circle(frame,pt,4 if i in(5,9,13,17) else 2,c,-1)
        if csx is not None and csy is not None and sw>0 and sh>0:
            rx=(float(csx)-vx)/max(sw-1,1); ry=(float(csy)-vy)/max(sh-1,1)
            ax=int(max(0,min(1,rx))*(w-1)); ay=int(max(0,min(1,ry))*(h-1))
            cv2.drawMarker(frame,(ax,ay),(0,255,255),cv2.MARKER_CROSS,15,2)
    cv2.rectangle(frame,(0,0),(w,52),(20,20,20),-1)
    cv2.putText(frame,f"STATE: {state}",(10,20),cv2.FONT_HERSHEY_SIMPLEX,0.6,color,2)
    cv2.putText(frame,f"ACTION: {action or '-'}  CONF: {conf:.2f}",(10,44),cv2.FONT_HERSHEY_SIMPLEX,0.45,(200,200,200),1)
    hints={"IDLE":"Show peace sign (index+middle) to start",
        "MOVE":"Peace=move | Drop idx=L | Drop mid=R | Fist=drag | Ring=vol",
        "CLICKING":"Hold fist=drag | Peace=cancel","DRAGGING":"Peace sign to release",
        "SCROLLING":"Hand up/down to scroll","ZOOMING":"Hand up/down to zoom",
        "CLUTCH":"Recenter hand, peace sign to resume",
        "VOLUME":"Hand up=vol up | Hand down=vol down | Release ring to stop"}
    cv2.putText(frame,hints.get(state,""),(10,h-12),cv2.FONT_HERSHEY_SIMPLEX,0.33,(160,160,160),1)
    return frame

def controller_process(landmark_queue: mp.Queue, stop_event: mp.Event):
    _configure_file_logging()
    from gesture_fsm import GestureStateMachine
    import cv2
    from pynput.keyboard import Key, Controller as KB

    _log.info("Controller started")
    vx,vy,sw,sh=get_virtual_screen_bounds()
    _log.info("Desktop: %sx%s at (%s,%s)",sw,sh,vx,vy)

    kb=KB(); user32=ctypes.windll.user32
    fsm=GestureStateMachine()
    fx=OneEuroFilter(); fy=OneEuroFilter()

    gx=float(vx+sw//2); gy=float(vy+sh//2)  # last_good cursor
    cpx=gx; cpy=gy  # clutch position
    c_anx=0.5; c_any=0.5; r_nx=0.5; r_ny=0.5
    clutch_active=False
    # Drag: relative mode (like clutch) so cursor doesn't jump
    drag_anchor_nx=0.5; drag_anchor_ny=0.5  # palm pos when drag started
    drag_cursor_sx=gx; drag_cursor_sy=gy  # cursor pos when drag started
    prev_lm=None; dragging=False
    last_lm=None; last_st="IDLE"; last_act=None; last_conf=0.0
    last_ts=time.time(); prev_ts=None
    # Drag filter: heavier smoothing for stable dragging
    dfx=OneEuroFilter(fmin=3.0, beta=0.004)
    dfy=OneEuroFilter(fmin=3.0, beta=0.004)

    while not stop_event.is_set():
        try:
            try:
                ts,lm,conf=landmark_queue.get(timeout=0.033)
                last_ts=ts
            except queue.Empty:
                _show(last_lm,last_st,last_act,last_conf,vx,vy,sw,sh,gx,gy)
                continue

            dt=1.0/30.0 if prev_ts is None else max(1e-4,min(0.25,float(last_ts-prev_ts)))
            prev_ts=last_ts

            inputs=extract_inputs(lm,conf,prev_lm,dt=dt) if lm is not None else None
            st_before=last_st
            result=fsm.update(inputs)
            state=result["state"]; action=result["action"]
            last_st=state; last_act=action

            if lm is not None:
                prev_lm=lm.copy(); last_lm=lm.copy(); last_conf=conf

            # Clutch management
            if state=="CLUTCH" and st_before!="CLUTCH":
                cpx=gx; cpy=gy
                c_anx=(cpx-vx)/max(sw-1,1e-9); c_any=(cpy-vy)/max(sh-1,1e-9)
                clutch_active=True
            if action=="CLUTCH_RESUME" and inputs is not None:
                r_nx,r_ny=hand_to_norm(inputs["hand_cx"],inputs["hand_cy"])
            if state in ("IDLE","LOCKED"): clutch_active=False

            # Drag anchor: save palm position when entering CLICKING (fist)
            if state=="CLICKING" and st_before!="CLICKING" and inputs is not None:
                drag_anchor_nx,drag_anchor_ny=hand_to_norm(inputs["hand_cx"],inputs["hand_cy"])
                drag_cursor_sx=gx; drag_cursor_sy=gy
                dfx.reset(gx,last_ts); dfy.reset(gy,last_ts)

            # CURSOR: only track when MOVE+peace or DRAGGING
            is_peace=inputs.get("is_peace",False) if inputs else False
            track=(state=="MOVE" and is_peace) or state=="DRAGGING"
            tp_limit=ANTI_TP*float(sw)

            if track and lm is not None and inputs is not None:
                if state=="DRAGGING":
                    # Relative drag: cursor = frozen_pos + (current_palm - drag_anchor)
                    rnx,rny=hand_to_norm(inputs["hand_cx"],inputs["hand_cy"])
                    dx_norm=rnx-drag_anchor_nx
                    dy_norm=rny-drag_anchor_ny
                    rsx=drag_cursor_sx+dx_norm*max(sw-1,0)
                    rsy=drag_cursor_sy+dy_norm*max(sh-1,0)
                    # Use heavier drag filter
                    cx=dfx(rsx,last_ts); cy=dfy(rsy,last_ts)
                    # Tighter anti-teleport during drag (2%)
                    drag_tp=0.02*float(sw)
                    if st_before=="DRAGGING":
                        d=math.hypot(cx-gx,cy-gy)
                        if d>drag_tp: dfx.reset(gx,last_ts); dfy.reset(gy,last_ts); cx=gx; cy=gy
                elif clutch_active:
                    rnx,rny=hand_to_norm(inputs["hand_cx"],inputs["hand_cy"])
                    tnx=max(0.0,min(1.0,c_anx+rnx-r_nx))
                    tny=max(0.0,min(1.0,c_any+rny-r_ny))
                    rsx=vx+tnx*max(sw-1,0); rsy=vy+tny*max(sh-1,0)
                    if state!=st_before:
                        fx.reset(cpx,last_ts); fy.reset(cpy,last_ts); gx=cpx; gy=cpy
                    cx=fx(rsx,last_ts); cy=fy(rsy,last_ts)
                    if state==st_before:
                        d=math.hypot(cx-gx,cy-gy)
                        if d>tp_limit: fx.reset(gx,last_ts); fy.reset(gy,last_ts); cx=gx; cy=gy
                else:
                    rsx,rsy=palm_to_screen(inputs["hand_cx"],inputs["hand_cy"],vx,vy,sw,sh)
                    if state!=st_before:
                        fx.reset(rsx,last_ts); fy.reset(rsy,last_ts); gx=rsx; gy=rsy
                    cx=fx(rsx,last_ts); cy=fy(rsy,last_ts)
                    if state==st_before:
                        d=math.hypot(cx-gx,cy-gy)
                        if d>tp_limit: fx.reset(gx,last_ts); fy.reset(gy,last_ts); cx=gx; cy=gy

                gx=cx; gy=cy
                sx=int(max(vx,min(vx+sw-1,round(cx))))
                sy=int(max(vy,min(vy+sh-1,round(cy))))
                user32.SetCursorPos(sx,sy)

            # ACTIONS
            try:
                sx=int(max(vx,min(vx+sw-1,round(gx))))
                sy=int(max(vy,min(vy+sh-1,round(gy))))

                if action=="LEFT_CLICK":
                    user32.SetCursorPos(sx,sy)
                    user32.mouse_event(2,0,0,0,0); user32.mouse_event(4,0,0,0,0)
                    _log.info("LEFT CLICK at (%s,%s)",sx,sy)
                elif action=="RIGHT_CLICK":
                    user32.SetCursorPos(sx,sy)
                    user32.mouse_event(8,0,0,0,0); user32.mouse_event(16,0,0,0,0)
                    _log.info("RIGHT CLICK at (%s,%s)",sx,sy)
                elif action=="DOUBLE_CLICK":
                    user32.SetCursorPos(sx,sy)
                    user32.mouse_event(2,0,0,0,0); user32.mouse_event(4,0,0,0,0)
                    time.sleep(0.05)
                    user32.mouse_event(2,0,0,0,0); user32.mouse_event(4,0,0,0,0)
                    _log.info("DOUBLE CLICK at (%s,%s)",sx,sy)
                elif action=="DRAG_START":
                    user32.SetCursorPos(sx,sy); user32.mouse_event(2,0,0,0,0)
                    dragging=True; _log.info("DRAG START at (%s,%s)",sx,sy)
                elif action=="DRAGGING":
                    user32.SetCursorPos(sx,sy)
                elif action=="DRAG_END":
                    user32.SetCursorPos(sx,sy); user32.mouse_event(4,0,0,0,0)
                    dragging=False; _log.info("DRAG END at (%s,%s)",sx,sy)
                elif action=="SCROLL_UP": user32.mouse_event(0x0800,0,0,60,0)
                elif action=="SCROLL_DOWN": user32.mouse_event(0x0800,0,0,-60,0)
                elif action=="ZOOM_IN":
                    kb.press(Key.ctrl); user32.mouse_event(0x0800,0,0,60,0); kb.release(Key.ctrl)
                elif action=="ZOOM_OUT":
                    kb.press(Key.ctrl); user32.mouse_event(0x0800,0,0,-60,0); kb.release(Key.ctrl)
                elif action=="VOL_UP":
                    user32.keybd_event(0xAF,0,0,0); user32.keybd_event(0xAF,0,2,0)
                elif action=="VOL_DOWN":
                    user32.keybd_event(0xAE,0,0,0); user32.keybd_event(0xAE,0,2,0)
                elif action=="VOICE_TOGGLE":
                    kb.press(Key.cmd); kb.press('h'); kb.release('h'); kb.release(Key.cmd)
                    _log.info("VOICE TYPING TOGGLE (Win+H)")
            except Exception as e:
                _log.exception("Action error: %s",e)

            _show(last_lm,state,action,last_conf,vx,vy,sw,sh,gx,gy)
        except Exception:
            _log.exception("Controller loop error")

    if dragging:
        try: user32.mouse_event(4,0,0,0,0)
        except: pass
    try: cv2.destroyAllWindows()
    except: pass
    _log.info("Controller stopped")

def _show(lm,state,action,conf,vx,vy,sw,sh,cx,cy):
    import cv2
    c=np.zeros((480,640,3),dtype=np.uint8)
    c=draw_overlay(c,lm,state,action,conf,vx,vy,sw,sh,cx,cy)
    cv2.imshow("AURA",c); cv2.waitKey(1)
