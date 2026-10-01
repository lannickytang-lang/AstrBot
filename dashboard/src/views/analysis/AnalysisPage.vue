<template>
  <div class="analysis-page">
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
                  <img
                    v-if="conv.avatar"
                    :src="conv.avatar"
                    class="cust-ava"
                    referrerpolicy="no-referrer"
                  />
                  <template v-if="copyingKey === conv.key">
                    <input
                      id="id-copy-input"
                      class="id-copy-input"
                      :value="copyingText"
                      readonly
                      @blur="copyingKey = ''"
                    />
                  </template>
                  <span
                    v-else
                    class="conv-name"
                    :title="tm('record.copyId')"
                    @click.stop="startIdCopy(conv.key, conv.nickname || conv.customerId)"
                  >
                    {{ conv.nickname || conv.customerId }}
                  </span>
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
            <template v-if="picked">
              <img
                v-if="picked.avatar"
                :src="picked.avatar"
                class="cust-ava"
                referrerpolicy="no-referrer"
              />
              <template v-if="copyingKey === 'picked'">
                <input
                  id="id-copy-input"
                  class="id-copy-input"
                  :value="copyingText"
                  readonly
                  @blur="copyingKey = ''"
                />
              </template>
              <span
                v-else
                class="panel-badge"
                :title="tm('record.copyId')"
                style="cursor: pointer"
                @click="startIdCopy('picked', picked.nickname || picked.customerId)"
              >
                {{ picked.nickname || picked.customerId }}
              </span>
            </template>
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
</div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { analysisApi } from "@/api/v1";
import type { AnalysisScenario } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import {
  TIME_PRESETS,
  useConversationPicker,
} from "@/composables/useConversationPicker";
import ScenarioEditDialog from "./ScenarioEditDialog.vue";

const { tm } = useModuleI18n("features/analysis");
const router = useRouter();

const timePresets = TIME_PRESETS;

// Conversation filters/list/selection logic is shared with the chat
// 客服历史 drawer via useConversationPicker.
const {
  timePreset,
  customStart,
  customEnd,
  platformOptions,
  selectedPlatforms,
  keyword,
  selectedTypes,
  conversations,
  totalCount,
  page,
  totalPages,
  loading,
  selectAllPage,
  selectedSet,
  selectedKeys,
  pickedKey,
  picked,
  snackbar,
  notify,
  platformLabel,
  togglePlatform,
  toggleType,
  resetFilters,
  scheduleFetch,
  toggleSelect,
  pickConversation,
  startIdCopy,
  copyingKey,
  copyingText,
  loadFilterOptions,
  fetchConversations,
  buildFilterPayload,
  selectedRefs,
  formatTime,
} = useConversationPicker();

const scenarios = ref<AnalysisScenario[]>([]);
const selectedScenarioId = ref("intent");
const scenarioDialogOpen = ref(false);
const scope = ref<"all" | "selected">("all");
const starting = ref(false);

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

async function exportByFilter(format: "csv" | "jsonl") {
  if (scope.value === "selected" && !selectedKeys.value.length) {
    notify(tm("messages.noSelection"), "warning");
    return;
  }
  try {
    const payload =
      scope.value === "selected"
        ? {
            conversations: selectedRefs(),
            format,
          }
        : { ...buildFilterPayload(), format };
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
    const payload =
      scope.value === "selected"
        ? {
            conversations: selectedRefs(),
            scenario_id: selectedScenarioId.value,
          }
        : { ...buildFilterPayload(), scenario_id: selectedScenarioId.value };
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
  padding: 16px 16px 24px 0;
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
.cust-ava {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  background: rgba(var(--v-theme-on-surface), 0.1);
}
.conv-name {
  font-size: 12.8px;
  font-weight: 600;
  cursor: pointer;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conv-name:hover {
  color: rgb(var(--v-theme-primary));
}
.id-copy-input {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  background: rgb(var(--v-theme-primary));
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 3px 8px;
  outline: none;
  width: 240px;
  max-width: 40vw;
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
