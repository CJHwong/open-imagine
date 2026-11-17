import 'package:flutter/foundation.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'probe.dart';

/// The shade's view of a run. The studio page polls the progress route and
/// hands every answer here. A running run becomes one progress notice backed by
/// a foreground service; the end of it becomes one completion notice.
///
/// A running notice names only the media, the stage and the percentage. The
/// completion notice names the media, how the run ended, and the operation's short
/// id: a phone that queued several runs has to say which one ended.
class RunNotifications {
  RunNotifications._();

  static const _progressId = 1001;
  static const _doneId = 1002;
  static const _progressChannel = 'generation_progress';
  static const _doneChannel = 'generation_done';

  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  static bool _serviceRunning = false;
  static bool _runSeen = false;
  // The kind of the run being watched. The progress answer for a finished run has no
  // kind, so the completion notice would otherwise have nothing to name.
  static String _kind = '';
  static DateTime _updatedAt = DateTime.fromMillisecondsSinceEpoch(0);

  static Future<void> initialize() async {
    await _plugin.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
      ),
    );
    final android = _plugin
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >();
    await android?.createNotificationChannel(
      const AndroidNotificationChannel(
        _progressChannel,
        'Generation progress',
        description: 'A run that is still going.',
        importance: Importance.low,
        playSound: false,
        enableVibration: false,
        showBadge: false,
      ),
    );
    await android?.createNotificationChannel(
      const AndroidNotificationChannel(
        _doneChannel,
        'Generation finished',
        description: 'A run that has finished.',
        importance: Importance.defaultImportance,
      ),
    );
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: _progressChannel,
        channelName: 'Generation progress',
        channelDescription: 'A run that is still going.',
        channelImportance: NotificationChannelImportance.LOW,
        priority: NotificationPriority.LOW,
        enableVibration: false,
        playSound: false,
        onlyAlertOnce: true,
      ),
      iosNotificationOptions: const IOSNotificationOptions(
        showNotification: false,
      ),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.nothing(),
        allowWakeLock: true,
        allowAutoRestart: false,
      ),
    );
  }

  /// Android 13 and up asks once. Call this when a pairing exists, not at first
  /// launch, so the app has a studio to notify about.
  static Future<void> requestPermission() async {
    await _plugin
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >()
        ?.requestNotificationsPermission();
  }

  /// One poll's answer. A hidden run leaves nothing in the shade. A failed read
  /// leaves the last notice alone, because a slow pipe is not the end of a run.
  static Future<void> observe(
    ProgressReply reply, {
    RunOutcome? outcome,
  }) async {
    if (reply.hidden) {
      await clear();
      return;
    }
    final progress = reply.progress;
    if (progress == null) return;
    if (!progress.running) {
      if (_runSeen) await _finish(_kind, outcome);
      return;
    }
    _runSeen = true;
    _kind = progress.kind;
    final now = DateTime.now();
    if (now.difference(_updatedAt) < const Duration(seconds: 1)) return;
    _updatedAt = now;
    await _startService(progress);
    await _post(progress);
  }

  /// Called when the studio page closes. That page is the only caller that
  /// polls, so a closed page leaves nothing to update.
  static Future<void> clear() async {
    if (!_runSeen && !_serviceRunning) return;
    _runSeen = false;
    await _plugin.cancel(id: _progressId);
    await _stopService();
  }

  /// The service notification is the progress notification: both use one id and
  /// one channel, so the shade holds one line, not two.
  static Future<void> _startService(RunProgress progress) async {
    if (_serviceRunning) return;
    if (await FlutterForegroundTask.isRunningService) {
      _serviceRunning = true;
      return;
    }
    final result = await FlutterForegroundTask.startService(
      serviceId: _progressId,
      serviceTypes: const [ForegroundServiceTypes.dataSync],
      notificationTitle: _title(progress.kind),
      notificationText: _body(progress),
    );
    if (result is ServiceRequestSuccess) {
      _serviceRunning = true;
    } else if (result is ServiceRequestFailure) {
      if (kDebugMode) debugPrint('Foreground service failed: ${result.error}');
    }
  }

  static Future<void> _stopService() async {
    if (!_serviceRunning) return;
    _serviceRunning = false;
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.stopService();
    }
  }

  static Future<void> _post(RunProgress progress) async {
    await _plugin.show(
      id: _progressId,
      title: _title(progress.kind),
      body: _body(progress),
      notificationDetails: NotificationDetails(
        android: AndroidNotificationDetails(
          _progressChannel,
          'Generation progress',
          channelDescription: 'A run that is still going.',
          importance: Importance.low,
          priority: Priority.low,
          showProgress: true,
          maxProgress: progress.total,
          progress: progress.step,
          indeterminate: progress.total == 0,
          ongoing: true,
          onlyAlertOnce: true,
          autoCancel: false,
          playSound: false,
          enableVibration: false,
          showWhen: false,
        ),
      ),
    );
  }

  static Future<void> _finish(String kind, RunOutcome? outcome) async {
    _runSeen = false;
    await _plugin.cancel(id: _progressId);
    await _stopService();
    await _plugin.show(
      id: _doneId,
      title: completionTitle(kind, outcome?.status ?? ''),
      body: completionBody(outcome),
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          _doneChannel,
          'Generation finished',
          channelDescription: 'A run that has finished.',
          importance: Importance.defaultImportance,
          priority: Priority.defaultPriority,
          autoCancel: true,
        ),
      ),
    );
  }

  /// How the notice names the end of a run. Pure, so a test reads it without a plugin.
  static String completionTitle(String kind, String status) {
    final media = switch (kind) {
      'image' => 'Image',
      'video' => 'Video',
      'music' || 'voice' => 'Audio',
      _ => 'Generation',
    };
    return switch (status) {
      'succeeded' => '$media finished',
      'failed' => '$media failed',
      'cancelled' => '$media stopped',
      _ => '$media finished',
    };
  }

  static String completionBody(RunOutcome? outcome) {
    if (outcome == null) return 'Tap to return to the studio.';
    final status = switch (outcome.status) {
      'succeeded' => 'succeeded',
      'failed' => 'failed',
      'cancelled' => 'was stopped',
      _ => 'ended',
    };
    return 'Operation ${outcome.shortId} $status. Tap to return to the studio.';
  }

  static String _title(String kind) => switch (kind) {
    'image' => 'Generating an image',
    'video' => 'Generating a video',
    'music' || 'voice' => 'Generating audio',
    _ => 'Generating',
  };

  static String _body(RunProgress progress) {
    final stage = progress.stage == 'preparing' ? 'Preparing' : 'Running';
    return progress.total > 0 ? '$stage, ${progress.percent}%' : stage;
  }
}
