// The device's readings for the performance HUD's lines (gfx_vk_present.c) and the frame recording's columns (perf_android.c dm_perf_record_start): -1 = unknown
#pragma once
typedef struct { long cpu_mhz, gpu_mhz, gpu_busy; int thermal, battery, saver; } dm_sample;
// cpu_mhz: the prime core's clock (the core of the highest maximum clock); gpu_mhz, gpu_busy: KGSL's (Adreno); thermal: Android's thermal status (AThermal, API 30:
// 0 none, 1 light, 2 moderate, 3 severe, 4 critical, 5 emergency, 6 shutdown); battery: percent; saver: Battery Saver on. Reads sysfs and calls into Java: never on
// the present or the game's threads
void dm_perf_sample(dm_sample *s);
