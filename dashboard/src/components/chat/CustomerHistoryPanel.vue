<template>
  <v-navigation-drawer
    :model-value="props.modelValue"
    location="right"
    :width="460"
    temporary
    floating
    class="cust-history-drawer"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="chd-inner">
      <div class="chd-head">
        <div>
          <div class="chd-title">{{ tm("customerHistory.title") }}</div>
          <div class="chd-subtitle">{{ tm("customerHistory.subtitle") }}</div>
        </div>
        <v-btn icon variant="text" size="small" @click="$emit('update:modelValue', false)">
          <X :size="18" />
        </v-btn>
      </div>

      <div class="chd-filters">
        <div class="chips">
          <span
            v-for="preset in timePresets"
            :key="preset.key"
            class="chip"
            :class="{ on: timePreset === preset.key }"
            @click="timePreset = preset.key"
          >
            {{ tmAnalysis(`filters.${preset.label}`) }}
          </span>
        </div>
        <input
          v-model.trim="keyword"
          type="text"
          class="text-input"
          :placeholder="tmAnalysis('filters.keywordPlaceholder')"
          @input="scheduleFetch"
        />
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
          <span class="chip-sep" />
          <span
            class="chip"
            :class="{ on: selectedTypes.includes('FriendMessage') }"
            @click="toggleType('FriendMessage')"
          >
            {{ tmAnalysis("filters.friend") }}
          </span>
          <span
            class="chip"
            :class="{ on: selectedTypes.includes('GroupMessage') }"
            @click="toggleType('GroupMessage')"
          >
            {{ tmAnalysis("filters.group") }}
          </span>
        </div>
        <div class="chd-hit">
          <v-btn variant="text" size="x-small" @click="resetFilters">
            {{ tmAnalysis("filters.reset") }}
          </v-btn>
          <span class="hit-count">
            {{ tmAnalysis("filters.hitCount", { n: totalCount }) }}
          </span>
        </div>
      </div>

      <div class="chd-list">
        <div v-if="!loading && conversations.length === 0" class="list-empty">
          {{ tmAnalysis("list.noData") }}
        </div>
        <template v-for="conv in conversations" :key="conv.key">
          <div
            class="conv-row"
            :class="{ picked: pickedKey === conv.key }"
            @click="toggleExpand(conv)"
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
                <span class="conv-name" :title="conv.customerId">
                  {{ conv.nickname || conv.customerId }}
                </span>
                <span class="conv-msgs">
                  {{ tmAnalysis("list.messages", { n: conv.messageCount }) }}
                </span>
                <span class="conv-time">{{ formatTime(conv.updatedAt) }}</span>
              </div>
              <div class="conv-snippet">{{ conv.snippet }}</div>
            </div>
          </div>
          <div v-if="pickedKey === conv.key && picked" class="conv-record">
            <div
              v-for="(msg, idx) in picked.messages"
              :key="idx"
              class="msg"
              :class="{ user: msg.role === 'user' }"
            >
              <div class="ava" :class="msg.role === 'user' ? 'cust' : 'ai'">
                {{ msg.role === "user" ? tmAnalysis("record.customer") : tmAnalysis("record.bot") }}
              </div>
              <div class="bub">{{ msg.text }}</div>
            </div>
            <div v-if="!picked.messages.length" class="record-empty">
              {{ tmAnalysis("list.noData") }}
            </div>
          </div>
        </template>
      </div>

      <div class="chd-foot">
        <div class="chd-foot-hint">{{ tm("customerHistory.exportHint") }}</div>
        <div class="chd-foot-actions">
          <span class="scope-label">
            {{
              selectedKeys.length
                ? tm("customerHistory.exportSelected", { n: selectedKeys.length })
                : tm("customerHistory.exportAll", { n: totalCount })
            }}
          </span>
          <v-btn
            color="primary"
            :loading="props.exporting"
            :disabled="totalCount === 0"
            @click="emitExport"
          >
            {{ tm("customerHistory.export") }}
          </v-btn>
        </div>
      </div>
    </div>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { X } from "@lucide/vue";
import { useModuleI18n } from "@/i18n/composables";
import {
  TIME_PRESETS,
  useConversationPicker,
  type ConvRow,
} from "@/composables/useConversationPicker";

// Right-side chat drawer: pick customer-service conversations and export
// them as a JSON attachment into the chat input.
const props = defineProps<{
  modelValue: boolean;
  exporting?: boolean;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (
    e: "export",
    payload: Record<string, unknown>,
  ): void;
}>();

const { tm } = useModuleI18n("features/chat");
const { tm: tmAnalysis } = useModuleI18n("features/analysis");

const timePresets = TIME_PRESETS;

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
  loading,
  selectedSet,
  selectedKeys,
  pickedKey,
  picked,
  platformLabel,
  togglePlatform,
  toggleType,
  resetFilters,
  scheduleFetch,
  toggleSelect,
  pickConversation,
  buildFilterPayload,
  selectedRefs,
  formatTime,
  loadFilterOptions,
  fetchConversations,
} = useConversationPicker();

// Refresh on every open so newly created conversations show up.
let filterOptionsLoaded = false;
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    if (!filterOptionsLoaded) {
      filterOptionsLoaded = true;
      void loadFilterOptions().then(fetchConversations);
    } else {
      void fetchConversations();
    }
  },
  { immediate: true },
);

function toggleExpand(conv: ConvRow) {
  if (pickedKey.value === conv.key) {
    pickedKey.value = "";
    picked.value = null;
    return;
  }
  void pickConversation(conv);
}

function emitExport() {
  const refs = selectedRefs();
  const payload = refs.length ? { conversations: refs } : buildFilterPayload();
  emit("export", payload as Record<string, unknown>);
}
</script>

<style scoped>
.chd-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.chd-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 14px 16px 10px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.chd-title {
  font-size: 15px;
  font-weight: 600;
}
.chd-subtitle {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  margin-top: 2px;
}
.chd-filters {
  padding: 10px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.chip {
  padding: 3px 11px;
  border-radius: 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  color: rgba(var(--v-theme-on-surface), 0.7);
  cursor: pointer;
  font-size: 12px;
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
.chip-sep {
  width: 1px;
  height: 16px;
  background: rgba(var(--v-theme-on-surface), 0.15);
  margin: 0 2px;
}
.text-input {
  background: rgba(var(--v-theme-on-surface), 0.06);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  border-radius: 8px;
  color: rgb(var(--v-theme-on-surface));
  padding: 6px 11px;
  font-size: 12.5px;
  font-family: inherit;
  outline: none;
  width: 100%;
}
.text-input:focus {
  border-color: rgb(var(--v-theme-primary));
}
.chd-hit {
  display: flex;
  align-items: center;
  gap: 8px;
}
.hit-count {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.chd-list {
  flex: 1;
  overflow-y: auto;
}
.list-empty {
  padding: 40px 20px;
  text-align: center;
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-size: 12.5px;
}
.conv-row {
  display: flex;
  gap: 8px;
  padding: 9px 14px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.05);
  cursor: pointer;
  transition: background 0.12s;
  align-items: center;
}
.conv-row:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.conv-row.picked {
  background: rgba(var(--v-theme-primary), 0.1);
}
.row-check {
  flex-shrink: 0;
}
.row-check :deep(.v-selection-control) {
  min-height: 28px;
}
.conv-info {
  flex: 1;
  min-width: 0;
}
.conv-top {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 2px;
}
.cust-ava {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  background: rgba(var(--v-theme-on-surface), 0.1);
}
.conv-name {
  font-size: 12.5px;
  font-weight: 600;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conv-msgs {
  font-size: 10.5px;
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.1);
  border-radius: 8px;
  padding: 0 6px;
  flex-shrink: 0;
}
.conv-time {
  margin-left: auto;
  font-size: 10.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  flex-shrink: 0;
}
.conv-snippet {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-record {
  background: rgba(var(--v-theme-on-surface), 0.03);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  max-height: 300px;
  overflow-y: auto;
}
.msg {
  display: flex;
  gap: 8px;
  max-width: 92%;
}
.msg.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.ava {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  color: #fff;
  background: rgb(var(--v-theme-primary));
}
.ava.cust {
  background: rgba(82, 196, 26, 0.75);
}
.bub {
  border-radius: 4px 10px 10px 10px;
  padding: 7px 11px;
  font-size: 12px;
  line-height: 1.6;
  background: rgba(var(--v-theme-on-surface), 0.07);
  white-space: pre-wrap;
  word-break: break-word;
}
.msg.user .bub {
  background: rgba(var(--v-theme-primary), 0.18);
  border-radius: 10px 4px 10px 10px;
}
.record-empty {
  text-align: center;
  color: rgba(var(--v-theme-on-surface), 0.4);
  font-size: 12px;
  padding: 12px;
}
.chd-foot {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  padding: 10px 16px 14px;
}
.chd-foot-hint {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  margin-bottom: 8px;
}
.chd-foot-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.scope-label {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  flex: 1;
}
</style>
