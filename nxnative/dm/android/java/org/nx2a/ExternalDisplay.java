package org.nx2a;

import android.app.Activity;
import android.app.Presentation;
import android.content.Context;
import android.hardware.display.DisplayManager;
import android.os.Handler;
import android.os.Looper;
import android.view.Display;
import android.view.Surface;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.WindowManager;

/** Routes an optional presentation surface to the host; all calls run on the UI thread. */
public final class ExternalDisplay implements DisplayManager.DisplayListener {
    public interface Listener {
        void surfaceChanged(Surface surface, int width, int height);
        void surfaceLost();
    }

    private final Activity activity;
    private final DisplayManager displays;
    private final Listener listener;
    private Presentation presentation;
    private int displayId = Display.INVALID_DISPLAY;
    private boolean active;
    private boolean surfaceLive;

    public ExternalDisplay(Activity activity, Listener listener) {
        this.activity = activity;
        this.listener = listener;
        this.displays = (DisplayManager) activity.getSystemService(Context.DISPLAY_SERVICE);
    }

    public void start() {
        if (active || displays == null) return;
        active = true;
        displays.registerDisplayListener(this, new Handler(Looper.getMainLooper()));
        update();
    }

    public void stop() {
        if (!active) return;
        active = false;
        displays.unregisterDisplayListener(this);
        dismiss();
    }

    private void dismiss() {
        Presentation old = presentation;
        presentation = null;
        displayId = Display.INVALID_DISPLAY;
        if (surfaceLive) { surfaceLive = false; listener.surfaceLost(); }
        if (old != null) old.dismiss();
    }

    /** A screen built into the device. A handheld with two (the AYN Thor: "Screen-2", 1080x1240, below the main one) lists the second as a presentation display too,
     *  and the game must not move there: only a display that was plugged in or cast to counts. Display.getType() is hidden (TYPE_INTERNAL = 1); where the platform
     *  refuses it, the names Android gives its built-in screens decide. */
    public static boolean builtIn(Display d) {
        try {
            Object type = Display.class.getMethod("getType").invoke(d);
            if (type instanceof Integer) return (Integer) type == 1;
        } catch (Throwable e) { /* the name below */ }
        String name = d.getName();
        return name != null && (name.startsWith("Built-in") || name.matches("Screen-\\d+"));
    }

    /** The display's mode for the game: the most pixels (a 4K television's 3840x2160 rather than the 1080p it may start in), and at that size the refresh rate nearest
     *  60 Hz from above, which the game's 60 and 30 fps divide. Null when the display lists none. */
    public static Display.Mode bestMode(Display d) {
        Display.Mode best = null; long area = -1; float rate = 0;
        for (Display.Mode m : d.getSupportedModes()) {
            long a = (long) m.getPhysicalWidth() * m.getPhysicalHeight(); float r = m.getRefreshRate();
            boolean better = a > area || (a == area && (rate < 59.5f ? r > rate : r >= 59.5f && r < rate));
            if (better) { best = m; area = a; rate = r; }
        }
        return best;
    }

    static String describe(Display.Mode m) { return m == null ? "no mode" : m.getPhysicalWidth() + "x" + m.getPhysicalHeight() + "@" + Math.round(m.getRefreshRate()) + "Hz"; }

    /** The external display the game goes to: none of the built-in screens, and the one with the most pixels when several are connected. */
    public static Display pick(Display[] candidates) {
        Display best = null; long area = -1;
        for (Display d : candidates) {
            if (builtIn(d)) continue;
            Display.Mode m = bestMode(d);
            long a = m == null ? 0 : (long) m.getPhysicalWidth() * m.getPhysicalHeight();
            if (a > area) { best = d; area = a; }
        }
        return best;
    }

    private void update() {
        if (!active) return;
        Display selected = pick(displays.getDisplays(DisplayManager.DISPLAY_CATEGORY_PRESENTATION));
        if (selected == null) { dismiss(); return; }
        if (presentation != null && selected.getDisplayId() == displayId) return;
        dismiss();
        Presentation next = new Presentation(activity, selected);
        SurfaceView view = new SurfaceView(next.getContext());
        view.getHolder().addCallback(new SurfaceHolder.Callback() {
            @Override public void surfaceCreated(SurfaceHolder holder) { }
            @Override public void surfaceChanged(SurfaceHolder holder, int format, int width, int height) {
                if (presentation != next || !active) return;
                surfaceLive = true;
                listener.surfaceChanged(holder.getSurface(), width, height);
            }
            @Override public void surfaceDestroyed(SurfaceHolder holder) {
                if (presentation != next || !surfaceLive) return;
                surfaceLive = false;
                listener.surfaceLost();
            }
        });
        next.setContentView(view);
        // The television's best mode, asked for only when it is not in it already: another mode makes the television renegotiate the link (the seconds of
        // black a television shows when a source changes resolution), on top of the one it did when the cable went in. Android usually mirrors at the
        // television's preferred mode, and then nothing changes.
        Display.Mode mode = bestMode(selected), current = selected.getMode();
        boolean change = mode != null && (current == null || current.getModeId() != mode.getModeId());
        android.util.Log.i("nx2a-dual", "display \"" + selected.getName() + "\" in " + describe(current) + ", best " + describe(mode) + (change ? ": asking for it" : ": kept"));
        if (change && next.getWindow() != null) {
            WindowManager.LayoutParams lp = next.getWindow().getAttributes();
            lp.preferredDisplayModeId = mode.getModeId();
            next.getWindow().setAttributes(lp);
        }
        presentation = next;
        displayId = selected.getDisplayId();
        try { next.show(); }
        catch (RuntimeException e) { dismiss(); }
    }

    @Override public void onDisplayAdded(int id) { update(); }
    @Override public void onDisplayRemoved(int id) { update(); }
    @Override public void onDisplayChanged(int id) { update(); }
}
