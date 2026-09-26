package org.lineageos.karat.cecstartup;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;

/** One-time activation clears Android's newly installed/stopped package state. */
public final class EnableActivity extends Activity {
    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        sendBroadcast(new Intent(this, StartupReceiver.class)
                .setAction(StartupReceiver.ACTION_CHECK));
        finish();
    }
}
