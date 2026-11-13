package com.hoss.open_imagine_phone

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import java.io.File
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private lateinit var studioInputs: StudioInputs
    private external fun nativeInit(context: Context)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // iroh resolves names through Android's APIs. A standalone process has no
        // Java VM, so the pipe runs inside this app and receives both here.
        nativeInit(applicationContext)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        studioInputs = StudioInputs(this,
            MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "open_imagine/inputs"))
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "open_imagine/native")
            .setMethodCallHandler { call, result ->
                if (call.method == "nativeLibraryDir") {
                    result.success(applicationInfo.nativeLibraryDir)
                } else {
                    result.notImplemented()
                }
            }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "open_imagine/files")
            .setMethodCallHandler { call, result ->
                if (call.method == "save") {
                    val name = call.argument<String>("name") ?: "download"
                    val mime = call.argument<String>("mime") ?: "application/octet-stream"
                    val bytes = call.argument<ByteArray>("bytes") ?: ByteArray(0)
                    result.success(saveFile(name, mime, bytes))
                } else {
                    result.notImplemented()
                }
            }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        studioInputs.onRequestPermissionsResult(requestCode, grantResults)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, intent: Intent?) {
        super.onActivityResult(requestCode, resultCode, intent)
        studioInputs.onActivityResult(requestCode, resultCode, intent)
    }

    override fun onDestroy() {
        studioInputs.dispose()
        super.onDestroy()
    }

    private fun saveFile(name: String, mime: String, bytes: ByteArray): String {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, name)
                put(MediaStore.Downloads.MIME_TYPE, mime)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val uri = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: throw IllegalStateException("No Downloads collection")
            contentResolver.openOutputStream(uri)?.use { it.write(bytes) }
            values.clear()
            values.put(MediaStore.Downloads.IS_PENDING, 0)
            contentResolver.update(uri, values, null, null)
            return uri.toString()
        }
        val folder = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: filesDir
        folder.mkdirs()
        val file = File(folder, name)
        file.writeBytes(bytes)
        return file.absolutePath
    }

    companion object {
        init {
            System.loadLibrary("openimagine_pipe")
        }
    }
}
