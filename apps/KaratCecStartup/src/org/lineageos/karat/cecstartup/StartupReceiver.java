package org.lineageos.karat.cecstartup;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.hardware.hdmi.HdmiControlManager;
import android.hardware.hdmi.HdmiPlaybackClient;
import android.util.Log;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/** Announces this playback device once per completed boot, then releases the receiver. */
public final class StartupReceiver extends BroadcastReceiver {
    static final String ACTION_CHECK = "org.lineageos.karat.cecstartup.CHECK";
    private static final String TAG = "KaratCecStartup";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action) && !ACTION_CHECK.equals(action)) {
            return;
        }
        // Both broadcasts are background broadcasts. goAsync retains the receiver
        // while One Touch Play completes; total work is bounded below 30 seconds.
        PendingResult pending = goAsync();
        Context app = context.getApplicationContext();
        Log.i(TAG, "Received " + action);
        new Thread(() -> {
            try {
                // BOOT_COMPLETED follows framework startup. Allow CEC address
                // allocation to settle; the service also queues requests until ready.
                Thread.sleep(1500);
                HdmiControlManager manager =
                        (HdmiControlManager) app.getSystemService("hdmi_control");
                HdmiPlaybackClient client = manager == null ? null : manager.getPlaybackClient();
                if (client == null) {
                    Log.w(TAG, "No HDMI playback client; no action sent");
                    return;
                }
                CountDownLatch completed = new CountDownLatch(1);
                AtomicInteger result = new AtomicInteger(-1);
                Log.i(TAG, "Requesting one startup HDMI announcement");
                client.oneTouchPlay(value -> {
                    result.set(value);
                    completed.countDown();
                });
                if (completed.await(25, TimeUnit.SECONDS)) {
                    Log.i(TAG, "One Touch Play result=" + result.get());
                } else {
                    // Do not repeat an action whose eventual outcome is unknown.
                    Log.w(TAG, "One Touch Play callback timed out; no retry");
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                Log.w(TAG, "Startup HDMI announcement interrupted");
            } catch (RuntimeException failure) {
                Log.e(TAG, "Startup HDMI announcement failed", failure);
            } finally {
                pending.finish();
            }
        }, "KaratCecStartup").start();
    }
}
