<template>
  <v-main class="analysis-page">
    <div class="analysis-container">
      <!-- Page head -->
      <div class="page-head">
        <div>
          <h1 class="page-title">{{ tm('title') }}</h1>
          <div class="page-subtitle">{{ tm('subtitle') }}</div>
        </div>
      </div>

      <!-- Filter card -->
      <v-card class="filter-card" elevation="0">
        <div class="filter-row">
          <div class="f-group">
            <span class="f-label">{{ tm('filters.timeRange') }}</span>
            <div class="chips">
              <span
                v-for="preset in timePresets"
                :key="preset.key"
                class="chip"
                :class="{ on: timePreset === preset.key }"
                @click="timePreset = preset.key"
              >
                {{ tm(`filters.${preset.label}`) }}
              </span>
            </div>
            <div v-if="timePreset === 'custom'" class="custom-dates">
              <input
                v-model="customStart"
                type="date"
                class="date-input"
                :aria-label="tm('filters.customStart')"
              />
              <span class="date-sep">~</span>
              <input
                v-model="customEnd"
                type="date"
                class="date-input"
                :aria-label="tm('filters.customEnd')"
              />
            </div>
          </div>

          <div class="f-group">
            <span class="f-label">{{ tm('filters.platform') }}</span>
            <div class="chips">
              <span
                v-for="bot in platformOptions"
                :key="bot.id"
                class="chip"
                :class="{ on: selectedPlatforms.includes(bot.id) }"
                @click="togglePlatform(bot.id)"
              >
                {{ platformLabel(bot.id) }}
              </span>
            </div>
          </div>

          <div class="f-group">
            <span class="f-label">{{ tm('filters.keyword') }}</span>
            <input
              v-model.trim="keyword"
              type="text"
              class="text-input"
              :placeholder="tm('filters.keywordPlaceholder')"
              @input="scheduleFetch"
            />
          </div>

          <div class="f-group">
            <span class="f-label">{{ tm('filters.messageType') }}</span>
            <div class="chips">
              <span
                class="chip"
                :class="{ on: selectedTypes.includes('FriendMessage') }"
                @click="toggleType('FriendMessage')"
              >
                {{ tm('filters.friend') }}
              </span>
              <span
                class="chip"
                :class="{ on: selectedTypes.includes('GroupMessage') }"
                @click="toggleType('GroupMessage')"
              >
                {{ tm('filters.group') }}
              </span>
            </div>
          </div>

          <div class="f-actions">
            <v-btn variant="text" size="small" @click="resetFilters">
              {{ tm('filters.reset') }}
            </v-btn>
            <span class="hit-count">
              {{ tm('filters.hitCount', { n: totalCount }) }}
            </span>
          </div>
        </div>
      </v-card>

      <!-- Workspace: list + record preview -->
      <div class="workspace">
        <v-card class="panel" elevation="0">
          <div class="panel-head">
            <span class="panel-title">{{ tm('list.title') }}</span>
            <span class="panel-badge">
              {{ tm('list.selected', { sel: selectedKeys.length, total: totalCount }) }}
            </span>
            <div class="panel-head-right">
              <v-checkbox
                v-model="selectAllPage"
                density="compact"
                hide-details
                :label="tm('list.selectAllPage')"
                class="select-all-box"
              />
            </div>
          </div>
          <div class="conv-list">
            <div v-if="!loading && conversations.length === 0" class="list-empty">
              {{ tm('list.noData') }}
            </div>
            <div
              v-for="conv in conversations"
              :key="conv.key"
              class="conv-row"
              :class="{ picked: pickedKey === conv.key }"
              @click="pickConversation(conv)"
            >
              <v-checkbox
                :model-value="selectedSet.has(conv.key)"
                density="compact"
                hide-details
                class="row-check"
                @click.stop
                @update:model-value="toggleSelect(conv)"
              />
              <div class="conv-info">
                <div class="conv-top">
                  <span class="conv-id">{{ conv.customerId }}</span>
                  <span class="conv-msgs">
                    {{ tm('list.messages', { n: conv.messageCount }) }}
                  </span>
                  <span class="conv-time">{{ formatTime(conv.updatedAt) }}</span>
                </div>
                <div class="conv-snippet">{{ conv.snippet }}</div>
              </div>
            </div>
          </div>
          <div class="pager">
            <v-btn
              variant="text"
              size="small"
              :disabled="page <= 1"
              @click="page -= 1"
            >
              ‹
            </v-btn>
            <span>{{ page }} / {{ totalPages }}</span>
            <v-btn
              variant="text"
              size="small"
              :disabled="page >= totalPages"
              @click="page += 1"
            >
              ›
            </v-btn>
          </div>
        </v-card>

        <v-card class="panel" elevation="0">
          <div class="panel-head">
            <span class="panel-title">{{ tm('record.title') }}</span>
            <span v-if="picked" class="panel-badge mono">{{ picked.customerId }}</span>
            <div class="panel-head-right" v-if="picked">
              {{ tm('record.messages', { n: picked.messageCount }) }}
            </div>
          </div>
          <div v-if="!picked" class="record-empty">
            <div class="record-empty-icon">🗨️</div>
            <div>{{ tm('record.empty') }}</div>
            <div class="record-empty-hint">{{ tm('record.emptyHint') }}</div>
          </div>
          <div v-else class="record-list">
            <div
              v-for="(msg, idx) in picked.messages"
              :key="idx"
              class="msg"
              :class="{ user: msg.role === 'user' }"
            >
              <div class="ava" :class="msg.role === 'user' ? 'cust' : 'ai'">
                {{ msg.role === 'user' ? tm('record.customer') : tm('record.bot') }}
              </div>
              <div class="bub">{{ msg.text }}</div>
            </div>
          </div>
          <div class="record-foot">{{ tm('record.foot') }}</div>
        </v-card>
      </div>

      <!-- Sticky action bar -->
      <div class="action-bar">
        <div class="ab-group">
          <span class="ab-label">{{ tm('actions.scenario') }}</span>
          <select v-model="selectedScenarioId" class="text-input scenario-select">
            <option v-for="s in scenarios" :key="s.id" :value="s.id">
              {{ s.icon }} {{ s.name }}
            </option>
          </select>
          <v-btn variant="outlined" size="small" @click="scenarioDialogOpen = true">
            {{ tm('actions.instructions') }}
          </v-btn>
        </div>
        <div class="ab-sep" />
        <div class="ab-group">
          <span class="ab-label">{{ tm('actions.scope') }}</span>
          <div class="chips">
            <span
              class="chip"
              :class="{ on: scope === 'all' }"
              @click="scope = 'all'"
            >
              {{ tm('actions.scopeAll', { n: totalCount }) }}
            </span>
            <span
              class="chip"
              :class="{ on: scope === 'selected' }"
              @click="scope = 'selected'"
            >
              {{ tm('actions.scopeSelected', { n: selectedKeys.length }) }}
            </span>
          </div>
        </div>
        <div class="ab-right">
          <v-menu>
            <template #activator="{ props }">
              <v-btn variant="outlined" size="small" v-bind="props">
                {{ tm('actions.export') }} ▾
              </v-btn>
            </template>
            <v-list density="compact">
              <v-list-item @click="exportByFilter('csv')">
                <v-list-item-title>{{ tm('actions.exportCsv') }}</v-list-item-title>
              </v-list-item>
              <v-list-item @click="exportByFilter('jsonl')">
                <v-list-item-title>{{ tm('actions.exportJsonl') }}</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-menu>
          <v-btn
            color="primary"
            :loading="starting"
            @click="startAnalysis"
          >
            ✦ {{ tm('actions.start') }}
          </v-btn>
        </div>
      </div>
      <div class="start-hint">{{ tm('actions.startHint') }}</div>
    </div>

    <ScenarioEditDialog
      v-model="scenarioDialogOpen"
      :scenarios="scenarios"
      @changed="loadScenarios"
    />

    <v-snackbar v-model="snackbar.visible" :color="snackbar.color" timeout="3000">
      {{ snackbar.text }}
    </v-snackbar>
  </v-main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { analysisApi, conversationApi } from "@/api/v1";
import type { AnalysisScenario } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import ScenarioEditDialog from "./ScenarioEditDialog.vue";

const { tm } = useModuleI18n("features/analysis");
const router = useRouter();

interface ConvRow {
  key: string;
  userId: string;
  cid: string;
  customerId: string;
  messageCount: number;
  snippet: string;
  updatedAt: number;
}

interface RecordMessage {
  role: "user" | "assistant";
  text: string;
}

const timePresets = [
  { key: "today", label: "today" },
  { key: "7d", label: "last7Days" },
  { key: "30d", label: "last30Days" },
  { key: "custom", label: "custom" },
] as const;

const timePreset = ref<(typeof timePresets)[number]["key"]>("7d");
const customStart = ref("");
const customEnd = ref("");
const platformOptions = ref<Array<{ id: string; type: string }>>([]);
const selectedPlatforms = ref<string[]>(["wecom"]);
const keyword = ref("");
const selectedTypes = ref<string[]>(["FriendMessage"]);

const conversations = ref<ConvRow[]>([]);
const totalCount = ref(0);
const page = ref(1);
const pageSize = 20;
const loading = ref(false);
const selectAllPage = ref(false);
const selectedSet = ref(new Set<string>());
const pickedKey = ref("");
const picked = ref<(ConvRow & { messages: RecordMessage[] }) | null>(null);

const scenarios = ref<AnalysisScenario[]>([]);
const selectedScenarioId = ref("intent");
const scenarioDialogOpen = ref(false);
const scope = ref<"all" | "selected">("all");
const starting = ref(false);

const snackbar = ref({ visible: false, text: "", color: "success" });
const totalPages = computed(() => Math.max(1, Math.ceil(totalCount.value / pageSize)));
const selectedKeys = computed(() => Array.from(selectedSet.value));

let fetchTimer: ReturnType<typeof setTimeout> | null = null;

function notify(text: string, color = "success") {
  snackbar.value = { visible: true, text, color };
}

function platformLabel(id: string) {
  return tm(`platformNames.${id}`) || id;
}

function togglePlatform(id: string) {
  const index = selectedPlatforms.value.indexOf(id);
  if (index >= 0) selectedPlatforms.value.splice(index, 1);
  else selectedPlatforms.value.push(id);
  scheduleFetch();
}

function toggleType(type: string) {
  const index = selectedTypes.value.indexOf(type);
  if (index >= 0) selectedTypes.value.splice(index, 1);
  else selectedTypes.value.push(type);
  scheduleFetch();
}

function resetFilters() {
  timePreset.value = "7d";
  customStart.value = "";
  customEnd.value = "";
  selectedPlatforms.value = ["wecom"];
  selectedTypes.value = ["FriendMessage"];
  keyword.value = "";
  page.value = 1;
}

function timeRangeEpochs(): { created_after?: number; created_before?: number } {
  const now = Date.now();
  const dayStart = new Date();
  dayStart.setHours(0, 0, 0, 0);
  if (timePreset.value === "today") {
    return {
      created_after: Math.floor(dayStart.getTime() / 1000),
      created_before: Math.floor(now / 1000),
    };
  }
  if (timePreset.value === "7d") {
    return { created_after: Math.floor((now - 7 * 86400_000) / 1000) };
  }
  if (timePreset.value === "30d") {
    return { created_after: Math.floor((now - 30 * 86400_000) / 1000) };
  }
  const range: { created_after?: number; created_before?: number } = {};
  if (customStart.value) {
    range.created_after = Math.floor(
      new Date(`${customStart.value}T00:00:00`).getTime() / 1000,
    );
  }
  if (customEnd.value) {
    range.created_before = Math.floor(
      new Date(`${customEnd.value}T23:59:59`).getTime() / 1000,
    );
  }
  return range;
}

function buildFilterPayload() {
  const range = timeRangeEpochs();
  return {
    platforms: selectedPlatforms.value.slice(),
    message_types: selectedTypes.value.slice(),
    keyword: keyword.value,
    created_after: range.created_after,
    created_before: range.created_before,
  };
}

async function fetchConversations() {
  loading.value = true;
  try {
    const range = timeRangeEpochs();
    const res = await conversationApi.list({
      page: page.value,
      page_size: pageSize,
      platforms: selectedPlatforms.value.join(","),
      message_types: selectedTypes.value.join(","),
      keyword: keyword.value,
      created_after: range.created_after,
      created_before: range.created_before,
      sort_by: "updated_at",
      sort_order: "desc",
      include_history: true,
    });
    const data = res.data?.data ?? {};
    const rows: ConvRow[] = (data.conversations ?? []).map((item: any) => {
      const messages = parseMessages(item.history);
      return {
        key: `${item.user_id}||${item.cid}`,
        userId: item.user_id,
        cid: item.cid,
        customerId: extractCustomerId(item.user_id),
        messageCount: messages.length,
        snippet:
          messages.find((m) => m.role === "user")?.text.slice(0, 80) ||
          item.title ||
          item.user_id,
        updatedAt: item.updated_at ?? 0,
      };
    });
    conversations.value = rows;
    totalCount.value = data.pagination?.total ?? rows.length;
    pruneSelection();
  } catch (error) {
    console.error("Failed to load conversations:", error);
  } finally {
    loading.value = false;
  }
}

function scheduleFetch() {
  if (fetchTimer) clearTimeout(fetchTimer);
  fetchTimer = setTimeout(() => {
    page.value = 1;
    fetchConversations();
  }, 320);
}

function extractCustomerId(userId: string) {
  const tail = String(userId || "").split(":").pop() || "";
  return tail.includes("!") ? tail.split("!").pop()! : tail;
}

function pruneSelection() {
  const valid = new Set(conversations.value.map((c) => c.key));
  for (const key of Array.from(selectedSet.value)) {
    if (!valid.has(key)) selectedSet.value.delete(key);
  }
}

watch(selectAllPage, (checked) => {
  for (const conv of conversations.value) {
    if (checked) selectedSet.value.add(conv.key);
    else selectedSet.value.delete(conv.key);
  }
});

watch([timePreset, customStart, customEnd], scheduleFetch);
watch(page, fetchConversations);

function toggleSelect(conv: ConvRow) {
  if (selectedSet.value.has(conv.key)) selectedSet.value.delete(conv.key);
  else selectedSet.value.add(conv.key);
}

function formatTime(epoch: number) {
  if (!epoch) return "";
  const d = new Date(epoch * 1000);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

async function pickConversation(conv: ConvRow) {
  pickedKey.value = conv.key;
  try {
    const res = await conversationApi.get(conv.userId, conv.cid);
    picked.value = { ...conv, messages: parseMessages(res.data?.data?.history) };
  } catch (error) {
    console.error("Failed to load conversation detail:", error);
  }
}

function parseMessages(historyText: unknown): RecordMessage[] {
  let history: any[] = [];
  try {
    history = typeof historyText === "string" ? JSON.parse(historyText) : historyText;
    if (!Array.isArray(history)) history = [];
  } catch {
    history = [];
  }
  const messages: RecordMessage[] = [];
  for (const item of history) {
    const role = item?.role;
    if (role !== "user" && role !== "assistant") continue;
    const text = extractText(item.content);
    if (!text || text.startsWith("<system")) continue;
    messages.push({ role, text });
  }
  return messages;
}

function extractText(content: unknown): string {
  let text = "";
  if (typeof content === "string") text = content.trim();
  else if (Array.isArray(content)) {
    text = content
      .filter(
        (p: any) =>
          (p?.type === "text" || p?.type === "plain") && typeof p?.text === "string",
      )
      .map((p: any) => p.text)
      .join("\n")
      .trim();
  }
  // System reminders may be appended to user messages; strip everything
  // from the first injected marker onward.
  if (text.includes("<system")) {
    text = text.split("<system", 1)[0].trim();
  }
  return text;
}

async function loadScenarios() {
  try {
    const res = await analysisApi.listScenarios();
    scenarios.value = res.data?.data ?? [];
    if (!scenarios.value.some((s) => s.id === selectedScenarioId.value)) {
      selectedScenarioId.value = scenarios.value[0]?.id ?? "intent";
    }
  } catch (error) {
    console.error("Failed to load scenarios:", error);
  }
}

async function loadFilterOptions() {
  try {
    const res = await conversationApi.filterOptions();
    const bots = res.data?.data?.bots ?? [];
    platformOptions.value = bots;
    if (!bots.some((b: any) => selectedPlatforms.value.includes(b.id))) {
      selectedPlatforms.value = bots.length ? [bots[0].id] : [];
    }
  } catch (error) {
    console.error("Failed to load filter options:", error);
  }
}

async function exportByFilter(format: "csv" | "jsonl") {
  if (scope.value === "selected" && !selectedKeys.value.length) {
    notify(tm("messages.noSelection"), "warning");
    return;
  }
  try {
    const base = buildFilterPayload();
    const payload =
      scope.value === "selected"
        ? {
            conversations: conversations.value
              .filter((c) => selectedSet.value.has(c.key))
              .map((c) => ({ user_id: c.userId, cid: c.cid })),
            format,
          }
        : { ...base, format };
    const response = await analysisApi.exportByFilter(payload as any);
    const url = window.URL.createObjectURL(response.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = `astrbot_analysis_export_${Date.now()}.${format}`;
    link.click();
    window.URL.revokeObjectURL(url);
    notify(tm("messages.exportSuccess"));
  } catch (error: any) {
    console.error("Export failed:", error);
    notify(error?.response?.data?.message || String(error), "error");
  }
}

async function startAnalysis() {
  if (scope.value === "selected" && !selectedKeys.value.length) {
    notify(tm("messages.noSelection"), "warning");
    return;
  }
  starting.value = true;
  try {
    const base = buildFilterPayload();
    const payload =
      scope.value === "selected"
        ? {
            conversations: conversations.value
              .filter((c) => selectedSet.value.has(c.key))
              .map((c) => ({ user_id: c.userId, cid: c.cid })),
            scenario_id: selectedScenarioId.value,
          }
        : { ...base, scenario_id: selectedScenarioId.value };
    const res = await analysisApi.createSession(payload as any);
    const result = res.data?.data;
    if (!result?.session_id) throw new Error("no session_id returned");
    notify(tm("messages.createSuccess"));
    await router.push({
      path: `/chat/${result.session_id}`,
      query: { autoSend: result.opening_instruction },
    });
  } catch (error: any) {
    console.error("Failed to create analysis session:", error);
    notify(error?.response?.data?.message || String(error), "error");
  } finally {
    starting.value = false;
  }
}

onMounted(async () => {
  await Promise.all([loadFilterOptions(), loadScenarios()]);
  await fetchConversations();
});
</script>

<style scoped>
.analysis-page {
  background: rgb(var(--v-theme-background));
  min-height: 100vh;
}
.analysis-container {
  padding: 20px 24px 28px;
  max-width: 1600px;
  margin: 0 auto;
}
.page-head {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  margin-bottom: 16px;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
}
.page-subtitle {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 12.5px;
  margin-top: 2px;
}
.filter-card,
.panel {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 12px;
}
.filter-card {
  padding: 16px 18px;
}
.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  align-items: flex-start;
}
.f-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.f-label {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.chip {
  padding: 5px 13px;
  border-radius: 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  color: rgba(var(--v-theme-on-surface), 0.7);
  cursor: pointer;
  font-size: 12.5px;
  transition: all 0.15s;
  user-select: none;
}
.chip:hover {
  border-color: rgba(var(--v-theme-on-surface), 0.45);
}
.chip.on {
  background: rgba(var(--v-theme-primary), 0.15);
  border-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-primary));
  font-weight: 500;
}
.custom-dates {
  display: flex;
  align-items: center;
  gap: 8px;
}
.date-sep {
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.date-input,
.text-input {
  background: rgba(var(--v-theme-on-surface), 0.06);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  border-radius: 8px;
  color: rgb(var(--v-theme-on-surface));
  padding: 7px 12px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
}
.date-input:focus,
.text-input:focus {
  border-color: rgb(var(--v-theme-primary));
}
.f-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}
.hit-count {
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.workspace {
  display: grid;
  grid-template-columns: minmax(340px, 5fr) minmax(420px, 7fr);
  gap: 16px;
  margin-top: 16px;
  align-items: stretch;
}
@media (max-width: 1100px) {
  .workspace {
    grid-template-columns: 1fr;
  }
}
.panel {
  display: flex;
  flex-direction: column;
  min-height: 520px;
  overflow: hidden;
}
.panel-head {
  padding: 14px 16px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.panel-title {
  font-weight: 600;
  font-size: 14.5px;
}
.panel-badge {
  background: rgba(var(--v-theme-primary), 0.15);
  color: rgb(var(--v-theme-primary));
  border-radius: 12px;
  padding: 1px 9px;
  font-size: 11.5px;
}
.panel-badge.mono {
  font-family: Consolas, Monaco, monospace;
}
.panel-head-right {
  margin-left: auto;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.select-all-box {
  margin-top: 0;
  padding-top: 0;
}
.select-all-box :deep(.v-selection-control) {
  min-height: 28px;
}
.select-all-box :deep(.v-label) {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.row-check {
  flex-shrink: 0;
}
.row-check :deep(.v-selection-control) {
  min-height: 30px;
}
.conv-list {
  overflow-y: auto;
  flex: 1;
}
.list-empty,
.record-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  padding: 40px;
  font-size: 13px;
  text-align: center;
}
.record-empty-icon {
  font-size: 38px;
  opacity: 0.5;
}
.record-empty-hint {
  font-size: 12px;
  opacity: 0.8;
}
.conv-row {
  display: flex;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.05);
  cursor: pointer;
  transition: background 0.12s;
  align-items: center;
}
.conv-row:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.conv-row.picked {
  background: rgba(var(--v-theme-primary), 0.12);
  box-shadow: inset 3px 0 0 rgb(var(--v-theme-primary));
}
.conv-info {
  flex: 1;
  min-width: 0;
}
.conv-top {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 3px;
}
.conv-id {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
}
.conv-msgs {
  font-size: 11px;
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.1);
  border-radius: 8px;
  padding: 0 6px;
  flex-shrink: 0;
}
.conv-time {
  margin-left: auto;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  flex-shrink: 0;
}
.conv-snippet {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.65);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.record-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.msg {
  display: flex;
  gap: 9px;
  max-width: 88%;
}
.msg.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.ava {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: #fff;
  background: rgb(var(--v-theme-primary));
}
.ava.cust {
  background: rgba(82, 196, 26, 0.75);
}
.bub {
  border-radius: 4px 12px 12px 12px;
  padding: 9px 13px;
  font-size: 12.8px;
  line-height: 1.7;
  background: rgba(var(--v-theme-on-surface), 0.07);
  white-space: pre-wrap;
  word-break: break-word;
}
.msg.user .bub {
  background: rgba(var(--v-theme-primary), 0.18);
  border-radius: 12px 4px 12px 12px;
}
.record-foot {
  padding: 10px 20px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.action-bar {
  position: sticky;
  bottom: 12px;
  z-index: 20;
  margin-top: 16px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 12px;
  padding: 12px 18px;
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
}
.ab-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.ab-label {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.ab-sep {
  width: 1px;
  height: 24px;
  background: rgba(var(--v-theme-on-surface), 0.15);
}
.scenario-select {
  cursor: pointer;
  min-width: 220px;
}
.ab-right {
  margin-left: auto;
  display: flex;
  gap: 10px;
  align-items: center;
}
.start-hint {
  text-align: center;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.4);
  margin-top: 8px;
}
</style>
