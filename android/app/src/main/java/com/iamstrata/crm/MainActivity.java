package com.iamstrata.crm;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.view.Gravity;
import android.view.View;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.text.InputType;
import android.net.Uri;

public class MainActivity extends Activity {
    private WebView browser;
    private final String prefName = "strata_settings";
    private final String urlKey = "server_url";
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        String saved = getSharedPreferences(prefName, MODE_PRIVATE).getString(urlKey, "");
        if (saved.isEmpty()) showSetup(); else openServer(saved);
    }
    private void showSetup() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        layout.setPadding(42,42,42,42);
        layout.setBackgroundColor(Color.rgb(8,15,29));
        TextView title = new TextView(this);
        title.setText("I AM STRATA\nCOMMAND CRM");
        title.setTextSize(27);
        title.setTextColor(Color.WHITE);
        title.setGravity(Gravity.CENTER);
        layout.addView(title);
        TextView subtitle = new TextView(this);
        subtitle.setText("Connect to your secure CRM server to sign in.\nNo server has been configured yet.");
        subtitle.setGravity(Gravity.CENTER);
        subtitle.setPadding(0,30,0,30);
        subtitle.setTextColor(Color.LTGRAY);
        layout.addView(subtitle);
        Button connect = new Button(this);
        connect.setText("SET SERVER URL");
        connect.setOnClickListener(v -> promptServer());
        layout.addView(connect);
        setContentView(layout);
    }
    private void promptServer() {
        EditText field = new EditText(this);
        field.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        field.setSingleLine(true);
        field.setHint("https://your-crm.example.com");
        new AlertDialog.Builder(this).setTitle("CRM server URL")
          .setMessage("Use your own HTTPS deployment. Do not enter a password here.")
          .setView(field)
          .setNegativeButton("Cancel", (d,w) -> {})
          .setPositiveButton("Connect", (d,w) -> {
              String value = field.getText().toString().trim();
              Uri uri = Uri.parse(value);
              if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null) {
                  new AlertDialog.Builder(this).setMessage("A valid HTTPS URL is required.").setPositiveButton("OK",(a,b)->promptServer()).show();
                  return;
              }
              getSharedPreferences(prefName, MODE_PRIVATE).edit().putString(urlKey, value).apply();
              openServer(value);
          }).show();
    }
    private void openServer(String url) {
        browser = new WebView(this);
        browser.getSettings().setJavaScriptEnabled(true);
        browser.getSettings().setDomStorageEnabled(true);
        browser.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri uri = req.getUrl();
                return !("https".equalsIgnoreCase(uri.getScheme()) && Uri.parse(url).getHost().equalsIgnoreCase(uri.getHost()));
            }
        });
        browser.loadUrl(url);
        setContentView(browser);
    }
    @Override public void onBackPressed() {
        if (browser != null && browser.canGoBack()) browser.goBack();
        else new AlertDialog.Builder(this).setTitle("IAmStrata CRM")
            .setItems(new String[]{"Change server", "Close"}, (d,which) -> {
                if(which==0) promptServer(); else finish();
            }).show();
    }
}
