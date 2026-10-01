import { computed, nextTick, ref, watch } from "vue";
import { analysisApi, conversationApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";

// Shared conversation-picker logic for the data-analysis page and the chat
// 客服历史 drawer: filter state, paged fetching, customer name resolution,
// selection bookkeeping and the inline record preview.

export interface ConvRow {
  key: string;
  userId: string;
  cid: string;
  customerId: string;
  nickname: string;
  avatar: string;
  messageCount: number;
  snippet: string;
  updatedAt: number;
}

export interface RecordMessage {
  role: "user" | "assistant";
  text: string;
}

export interface ConversationFilterPayload {
  platforms: string[];
  message_types: string[];
  keyword: string;
  created_after?: number;
  created_before?: number;
}

export interface ConversationRefPayload {
  user_id: string;
  cid: string;
}

export const TIME_PRESETS = [
  { key: "today", label: "today" },
  { key: "7d", label: "last7Days" },
  { key: "30d", label: "last30Days" },
  { key: "custom", label: "custom" },
] as const;

export type TimePresetKey = (typeof TIME_PRESETS)[number]["key"];

export function parseMessages(historyText: unknown): RecordMessage[] {
  let history: any[] = [];
  try {
    history =
      typeof historyText === "string" ? JSON.parse(historyText) : historyText;
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

export function extractText(content: unknown): string {
  let text = "";
  if (typeof content === "string") text = content.trim();
  else if (Array.isArray(content)) {
    text = content
      .filter(
        (p: any) =>
          (p?.type === "text" || p?.type === "plain") &&
          typeof p?.text === "string",
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

export function extractCustomerId(userId: string) {
  const tail = String(userId || "").split(":").pop() || "";
  return tail.includes("!") ? tail.split("!").pop()! : tail;
}

export function useConversationPicker() {
  const { tm } = useModuleI18n("features/analysis");

  const timePreset = ref<TimePresetKey>("7d");
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

  const totalPages = computed(() =>
    Math.max(1, Math.ceil(totalCount.value / pageSize)),
  );
  const selectedKeys = computed(() => Array.from(selectedSet.value));

  let fetchTimer: ReturnType<typeof setTimeout> | null = null;

  const snackbar = ref({ visible: false, text: "", color: "success" });

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

  function timeRangeEpochs(): {
    created_after?: number;
    created_before?: number;
  } {
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

  function buildFilterPayload(): ConversationFilterPayload {
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
      const rows: ConvRow[] = (data.conversations ?? [])
        // Analysis sessions themselves are corpus, not customer data.
        .filter((item: any) => item.persona_id !== "marketing_analyst")
        .map((item: any) => {
          const messages = parseMessages(item.history);
          return {
            key: `${item.user_id}||${item.cid}`,
            userId: item.user_id,
            cid: item.cid,
            customerId: extractCustomerId(item.user_id),
            nickname: "",
            avatar: "",
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
      void applyCustomerNames();
    } catch (error) {
      console.error("Failed to load conversations:", error);
    } finally {
      loading.value = false;
    }
  }

  async function applyCustomerNames() {
    const ids = Array.from(
      new Set(conversations.value.map((c) => c.customerId).filter(Boolean)),
    );
    if (!ids.length) return;
    try {
      const res = await analysisApi.customerNames(ids);
      const names = res.data?.data ?? {};
      for (const conv of conversations.value) {
        const info = names[conv.customerId];
        if (info) {
          conv.nickname = info.nickname || "";
          conv.avatar = info.avatar || "";
        }
      }
      if (picked.value) {
        const info = names[picked.value.customerId];
        if (info) {
          picked.value.nickname = info.nickname || "";
          picked.value.avatar = info.avatar || "";
        }
      }
    } catch (error) {
      // Name resolution is best effort; fall back to raw customer IDs.
      console.warn("Failed to load customer names:", error);
    }
  }

  // Embedded webviews (e.g. the desktop app browser pane) often deny
  // clipboard focus, so instead of a clipboard API we reveal the customer ID
  // inside a pre-selected input — Ctrl+C / long-press copies it everywhere.
  const copyingKey = ref("");
  const copyingText = ref("");

  function startIdCopy(key: string, displayText: string) {
    copyingKey.value = key;
    copyingText.value = displayText;
    notify(tm("record.copyHint"));
    nextTick(() => {
      const input = document.getElementById("id-copy-input");
      if (input instanceof HTMLInputElement) {
        input.focus();
        input.select();
      }
    });
    window.setTimeout(() => {
      if (copyingKey.value === key) copyingKey.value = "";
    }, 8000);
  }

  function scheduleFetch() {
    if (fetchTimer) clearTimeout(fetchTimer);
    fetchTimer = setTimeout(() => {
      page.value = 1;
      fetchConversations();
    }, 320);
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
    if (!conv.nickname || !conv.avatar) void applyCustomerNames();
    try {
      const res = await conversationApi.get(conv.userId, conv.cid);
      picked.value = { ...conv, messages: parseMessages(res.data?.data?.history) };
    } catch (error) {
      console.error("Failed to load conversation detail:", error);
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

  /** Selected conversations as explicit refs; empty when nothing picked. */
  function selectedRefs(): ConversationRefPayload[] {
    return conversations.value
      .filter((c) => selectedSet.value.has(c.key))
      .map((c) => ({ user_id: c.userId, cid: c.cid }));
  }

  return {
    // filter state
    timePreset,
    customStart,
    customEnd,
    platformOptions,
    selectedPlatforms,
    keyword,
    selectedTypes,
    // list state
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
    // notifications
    snackbar,
    notify,
    // actions
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
  };
}
