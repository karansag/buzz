#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#import <UserNotifications/UserNotifications.h>
#import <dispatch/dispatch.h>
#include <stdio.h>

// Retain the delegate for the app's lifetime; UNUserNotificationCenter.delegate
// is weak. Rust copies the callback string before this method returns.
static void (*openAgent)(const char *) = NULL;
@interface SwarmNotificationDelegate : NSObject <UNUserNotificationCenterDelegate>
@end
static SwarmNotificationDelegate *notificationDelegate;

static void logError(const char *operation, NSError *error) {
    fprintf(stderr, "Buzz notifications: %s error=%s\n", operation,
            error ? error.description.UTF8String : "none");
    fflush(stderr);
}

static BOOL hasBundle(void) {
    if (NSBundle.mainBundle.bundleIdentifier.length) return YES;
    fprintf(stderr, "Buzz notifications: no bundle identifier; run the built .app\n");
    fflush(stderr);
    return NO;
}

// Logs the result when asked to, and always when permission is refused.
static void authorize(BOOL logResult, BOOL openSettingsIfDenied, void (^completion)(BOOL)) {
    if (!hasBundle()) { if (completion) completion(NO); return; }
    UNUserNotificationCenter *center = UNUserNotificationCenter.currentNotificationCenter;
    [center requestAuthorizationWithOptions:(UNAuthorizationOptionAlert |
                                            UNAuthorizationOptionSound |
                                            UNAuthorizationOptionBadge)
                         completionHandler:^(BOOL granted, NSError *error) {
        if (logResult || !granted) {
            fprintf(stderr, "Buzz notifications: authorization granted=%s error=%s\n",
                    granted ? "yes" : "no", error ? error.description.UTF8String : "none");
            fflush(stderr);
        }
        if (!granted && openSettingsIfDenied) {
            dispatch_async(dispatch_get_main_queue(), ^{
                [NSWorkspace.sharedWorkspace openURL:[NSURL URLWithString:
                    @"x-apple.systempreferences:com.apple.Notifications-Settings.extension"]];
            });
        }
        if (completion) completion(granted);
    }];
}

@implementation SwarmNotificationDelegate
- (void)userNotificationCenter:(UNUserNotificationCenter *)center
      willPresentNotification:(UNNotification *)notification
        withCompletionHandler:(void (^)(UNNotificationPresentationOptions))completionHandler {
    // Foreground notifications are hidden by default without this delegate.
    if (@available(macOS 11.0, *)) {
        completionHandler(UNNotificationPresentationOptionBanner |
                          UNNotificationPresentationOptionList |
                          UNNotificationPresentationOptionSound);
    } else {
        completionHandler(UNNotificationPresentationOptionAlert |
                          UNNotificationPresentationOptionSound);
    }
}

- (void)userNotificationCenter:(UNUserNotificationCenter *)center
 didReceiveNotificationResponse:(UNNotificationResponse *)response
         withCompletionHandler:(void (^)(void))completionHandler {
    if ([response.actionIdentifier isEqualToString:UNNotificationDefaultActionIdentifier]) {
        NSString *agent = response.notification.request.content.userInfo[@"agent"];
        if ([agent isKindOfClass:NSString.class] && openAgent) openAgent(agent.UTF8String);
    }
    completionHandler();
}
@end

static void sendNotification(NSString *agent) {
    // Strings are copied to ARC-owned objects before this async operation.
    // Calling requestAuthorization again does not reprompt after a decision;
    // it ensures the first attention update waits for the initial grant.
    authorize(NO, NO, ^(BOOL granted) {
        if (!granted) return;
        UNMutableNotificationContent *content = [UNMutableNotificationContent new];
        content.title = agent ? @"Agent needs attention" : @"Buzz notifications";
        content.body = agent ? [NSString stringWithFormat:@"%@ is waiting for you.", agent]
                             : @"Notifications are enabled. Your swarm can reach you here.";
        content.sound = UNNotificationSound.defaultSound;
        if (agent) content.userInfo = @{@"agent": agent};
        // One notification per agent: a newer one replaces the older.
        UNNotificationRequest *request = [UNNotificationRequest
            requestWithIdentifier:(agent ?: @"test") content:content trigger:nil];
        [UNUserNotificationCenter.currentNotificationCenter addNotificationRequest:request
            withCompletionHandler:^(NSError *error) {
                if (error) logError("delivery", error);
                else {
                    fprintf(stderr, "Buzz notifications: queued %s\n",
                            agent ? agent.UTF8String : "test");
                    fflush(stderr);
                }
            }];
    });
}

void swarm_notifications_init(void (*callback)(const char *)) {
    @autoreleasepool {
        openAgent = callback;
        if (!hasBundle()) return;
        notificationDelegate = [SwarmNotificationDelegate new];
        UNUserNotificationCenter.currentNotificationCenter.delegate = notificationDelegate;
        authorize(YES, NO, nil);
    }
}

void swarm_notifications_enable(void) {
    @autoreleasepool { authorize(YES, YES, nil); }
}

void swarm_notifications_send(const char *agent) {
    @autoreleasepool {
        NSString *name = agent ? [NSString stringWithUTF8String:agent] : nil;
        if (name) sendNotification(name);
    }
}

void swarm_notifications_test(void) {
    @autoreleasepool { sendNotification(nil); }
}
