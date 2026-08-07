/*********************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2009-2026 Jason Neuswanger
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 ***********************************************************************************/

#import "VSCrashReporter.h"
#import <execinfo.h>
#import <fcntl.h>
#import <unistd.h>
#import <signal.h>
#import <cxxabi.h>
#import <exception>
#import <typeinfo>
#import <string>

// The recipient address, base64-encoded so the raw address doesn't sit in the public repository
// for scrapers to harvest; it is decoded only at the moment the user chooses to send a report.
static NSString *const VSCrashReportRecipientBase64 = @"amFzb25uZXVzd2FuZ2VyQGdtYWlsLmNvbQ==";

// State the signal handler needs, prepared at install time because a crashed process can only
// safely call async-signal-safe functions (open/write/backtrace_symbols_fd), not Objective-C.
static char vsCrashReportPath[PATH_MAX];
static char vsCrashReportHeader[512];
static NSUncaughtExceptionHandler *vsPreviousExceptionHandler = NULL;
static std::terminate_handler vsPreviousTerminateHandler = NULL;
static volatile sig_atomic_t vsCrashReportWritten = 0;	// an uncaught exception ends in abort(), and SIGABRT must not overwrite the richer exception report

static const int vsCrashSignals[] = {SIGSEGV,SIGBUS,SIGILL,SIGFPE,SIGABRT,SIGTRAP};

static void VSCrashSignalHandler(int signalNumber)
{
	int fd = vsCrashReportWritten ? -1 : open(vsCrashReportPath,O_CREAT|O_WRONLY|O_TRUNC,0644);
	if (fd >= 0) {
		write(fd,vsCrashReportHeader,strlen(vsCrashReportHeader));
		const char *signalName = "unknown";
		switch (signalNumber) {
			case SIGSEGV: signalName = "SIGSEGV (bad memory access)"; break;
			case SIGBUS: signalName = "SIGBUS (bus error)"; break;
			case SIGILL: signalName = "SIGILL (illegal instruction)"; break;
			case SIGFPE: signalName = "SIGFPE (arithmetic error)"; break;
			case SIGABRT: signalName = "SIGABRT (abort)"; break;
			case SIGTRAP: signalName = "SIGTRAP (trap)"; break;
		}
		write(fd,"Fatal signal: ",14);
		write(fd,signalName,strlen(signalName));
		write(fd,"\n\nBacktrace:\n",13);
		void *frames[128];
		int frameCount = backtrace(frames,128);
		backtrace_symbols_fd(frames,frameCount,fd);
		close(fd);
	}
	signal(signalNumber,SIG_DFL);	// let the default handler terminate the process (and macOS write its own report)
	raise(signalNumber);
}

static void VSCrashExceptionHandler(NSException *exception)
{
	// Objective-C is not strictly safe here either, but an uncaught exception leaves the runtime in
	// a far saner state than a fatal signal, and this is the path with the useful symbolic stack.
	NSString *report = [NSString stringWithFormat:@"%sUncaught exception: %@\nReason: %@\n\nBacktrace:\n%@\n",
					vsCrashReportHeader,
					[exception name],
					[exception reason],
					[[exception callStackSymbols] componentsJoinedByString:@"\n"]];
	if ([report writeToFile:[NSString stringWithUTF8String:vsCrashReportPath] atomically:YES encoding:NSUTF8StringEncoding error:NULL]) vsCrashReportWritten = 1;
	if (vsPreviousExceptionHandler != NULL) vsPreviousExceptionHandler(exception);
}

// The Objective-C runtime's terminate handler reports Objective-C exceptions through the handler
// installed by NSSetUncaughtExceptionHandler, which is how VSCrashExceptionHandler above gets a
// name, a reason and a symbolic stack. A C++ exception is not an Objective-C object, so it takes
// that runtime's "not one of mine" branch and the process aborts having reported nothing: the
// resulting file says only "Fatal signal: SIGABRT" over a backtrace of the abort path. That is
// exactly what a cv::Exception out of the OpenCV calibration code looked like from here, and it
// cost a release to work out. This handler runs first, records what the C++ exception actually
// was, and then chains to the runtime's handler so the Objective-C path behaves as before.
static void VSCrashTerminateHandler(void)
{
	const std::type_info *exceptionType = __cxxabiv1::__cxa_current_exception_type();

	// Objective-C exceptions are thrown as `id`. Leave those completely alone -- not just
	// unreported but untouched, because rethrowing to inspect one can consume it, and the
	// Objective-C handler further down the chain needs it still in flight to do its job.
	BOOL isObjectiveC = (exceptionType != NULL && *exceptionType == typeid(id));

	if (exceptionType != NULL && !isObjectiveC) {
		std::string typeName = exceptionType->name();
		int demangleStatus = 0;
		char *demangled = __cxxabiv1::__cxa_demangle(exceptionType->name(), NULL, NULL, &demangleStatus);
		if (demangleStatus == 0 && demangled != NULL) typeName = demangled;
		if (demangled != NULL) free(demangled);

		std::string message;
		try {
			throw;	// safe: checked above that an exception is in flight, and nothing escapes
		} catch (const std::exception &e) {
			if (e.what() != NULL) message = e.what();
		} catch (...) {
		}

		NSString *report = [NSString stringWithFormat:
						@"%sUncaught C++ exception: %s\nReason: %s\n\nBacktrace:\n%@\n\n"
						 "Note: the backtrace above is the stack at abort, not at the throw. A C++ exception that\n"
						 "passed through an AppKit @catch on its way out has already had its throwing frames\n"
						 "unwound, so the exception type and reason are the identifying information here.\n",
						vsCrashReportHeader,
						typeName.c_str(),
						message.empty() ? "(the exception carried no message)" : message.c_str(),
						[[NSThread callStackSymbols] componentsJoinedByString:@"\n"]];
		if ([report writeToFile:[NSString stringWithUTF8String:vsCrashReportPath] atomically:YES encoding:NSUTF8StringEncoding error:NULL]) vsCrashReportWritten = 1;
	}

	if (vsPreviousTerminateHandler != NULL) vsPreviousTerminateHandler();
	abort();	// a terminate handler may not return; if the chained one did, end it here
}

@implementation VSCrashReporter

+ (NSString *) pendingReportPath
{
	NSString *appSupportFolder = [NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory,NSUserDomainMask,YES) firstObject];
	NSString *vidSyncFolder = [appSupportFolder stringByAppendingPathComponent:@"VidSync"];
	[[NSFileManager defaultManager] createDirectoryAtPath:vidSyncFolder withIntermediateDirectories:YES attributes:nil error:NULL];
	return [vidSyncFolder stringByAppendingPathComponent:@"PendingCrashReport.txt"];
}

+ (void) install
{
	NSDictionary *bundleInfo = [[NSBundle mainBundle] infoDictionary];
	NSOperatingSystemVersion osVersion = [[NSProcessInfo processInfo] operatingSystemVersion];
	snprintf(vsCrashReportHeader,sizeof(vsCrashReportHeader),
		 "VidSync crash report\nVidSync version: %s (%s)\nmacOS version: %ld.%ld.%ld\n\n",
		 [(bundleInfo[@"CFBundleShortVersionString"] ?: @"?") UTF8String],
		 [(bundleInfo[@"CFBundleVersion"] ?: @"?") UTF8String],
		 (long)osVersion.majorVersion,(long)osVersion.minorVersion,(long)osVersion.patchVersion);
	strlcpy(vsCrashReportPath,[[self pendingReportPath] fileSystemRepresentation],sizeof(vsCrashReportPath));

	vsPreviousExceptionHandler = NSGetUncaughtExceptionHandler();
	NSSetUncaughtExceptionHandler(&VSCrashExceptionHandler);
	// std::set_terminate returns the handler it displaces, which at this point is the Objective-C
	// runtime's. Keeping and calling it is what preserves Objective-C exception reporting.
	vsPreviousTerminateHandler = std::set_terminate(&VSCrashTerminateHandler);
	for (size_t i = 0; i < sizeof(vsCrashSignals)/sizeof(vsCrashSignals[0]); i++) signal(vsCrashSignals[i],&VSCrashSignalHandler);
}

+ (void) offerToSendPendingReport
{
	NSString *reportPath = [self pendingReportPath];
	NSString *report = [NSString stringWithContentsOfFile:reportPath encoding:NSUTF8StringEncoding error:NULL];
	if (report == nil) return;

	NSAlert *crashAlert = [NSAlert new];
	[crashAlert setMessageText:@"VidSync crashed the last time it ran"];
	[crashAlert setInformativeText:@"Sorry about that. Would you like to email the crash report to VidSync's developer so the problem can be fixed?\n\nThis opens a pre-filled message in your own email program, so you can read exactly what it contains (just technical details of the crash) and add a note about what you were doing before choosing whether to send it."];
	[crashAlert addButtonWithTitle:@"Email Crash Report"];
	[crashAlert addButtonWithTitle:@"Don't Send"];
	NSModalResponse response = [crashAlert runModal];
	if (response == NSAlertFirstButtonReturn) [self composeEmailWithReport:report];
	[[NSFileManager defaultManager] removeItemAtPath:reportPath error:NULL];	// either way, only offer each crash once
}

+ (void) composeEmailWithReport:(NSString *)report
{
	NSData *recipientData = [[NSData alloc] initWithBase64EncodedString:VSCrashReportRecipientBase64 options:0];
	NSString *recipient = [[NSString alloc] initWithData:recipientData encoding:NSUTF8StringEncoding];
	NSString *subject = @"VidSync crash report";
	NSString *body = [NSString stringWithFormat:@"(Optional: describe what you were doing when VidSync crashed.)\n\n\n----- Crash report -----\n\n%@",report];

	NSSharingService *emailService = [NSSharingService sharingServiceNamed:NSSharingServiceNameComposeEmail];
	emailService.recipients = @[recipient];
	emailService.subject = subject;
	if ([emailService canPerformWithItems:@[body]]) {
		[emailService performWithItems:@[body]];
	} else {
		// No compose-capable mail client registered; fall back to a mailto: URL, truncating the body
		// to stay within what URL handlers reliably accept.
		NSString *truncatedBody = ([body length] > 1800) ? [[body substringToIndex:1800] stringByAppendingString:@"\n[truncated]"] : body;
		NSURLComponents *mailto = [NSURLComponents new];
		mailto.scheme = @"mailto";
		mailto.path = recipient;
		mailto.queryItems = @[[NSURLQueryItem queryItemWithName:@"subject" value:subject],
						  [NSURLQueryItem queryItemWithName:@"body" value:truncatedBody]];
		if (mailto.URL != nil) [[NSWorkspace sharedWorkspace] openURL:mailto.URL];
	}
}

@end
