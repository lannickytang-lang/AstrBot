<template>
  <v-dialog
    :model-value="modelValue"
    max-width="760px"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6 dialog-title">
        {{ tm('dialog.title') }}
        <div class="dialog-subtitle">{{ tm('dialog.subtitle') }}</div>
      </v-card-title>
      <v-card-text class="pa-6">
        <div class="chips">
          <span
            v-for="s in localScenarios"
            :key="s.id || '__new__'"
            class="chip"
            :class="{ on: editing?.id === s.id }"
            @click="pick(s)"
          >
            {{ s.icon }} {{ s.name }}
            <span v-if="s.built_in" class="builtin-tag">内置</span>
          </span>
          <span class="chip new-chip" @click="startNew">
            {{ tm('dialog.newScene') }}
          </span>
        </div>

        <div class="field">
          <div class="field-row">
            <div class="field-grow">
              <div class="f-label">{{ tm('dialog.nameLabel') }}</div>
              <input v-model="form.name" type="text" class="text-input full" />
            </div>
            <div>
              <div class="f-label">{{ tm('dialog.iconLabel') }}</div>
              <input v-model="form.icon" type="text" class="text-input icon-input" />
            </div>
          </div>
        </div>

        <div class="field">
          <div class="f-label">{{ tm('dialog.descriptionLabel') }}</div>
          <input v-model="form.description" type="text" class="text-input full" />
        </div>

        <div class="field">
          <div class="f-label">{{ tm('dialog.instructionLabel') }}</div>
          <textarea v-model="form.instruction" rows="9" class="instruction-area" />
        </div>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-btn
          v-if="editing?.built_in"
          variant="text"
          @click="restore"
        >
          {{ tm('dialog.restore') }}
        </v-btn>
        <v-btn
          v-if="editing && !editing.built_in"
          variant="text"
          color="error"
          @click="remove"
        >
          {{ tm('dialog.deleteScene') }}
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="emit('update:modelValue', false)">
          {{ t('core.actions.close') }}
        </v-btn>
        <v-btn variant="tonal" color="primary" :loading="saving" @click="save">
          {{ tm('dialog.save') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { analysisApi } from "@/api/v1";
import type { AnalysisScenario } from "@/api/v1";
import { useI18n, useModuleI18n } from "@/i18n/composables";

const props = defineProps<{ modelValue: boolean; scenarios: AnalysisScenario[] }>();
const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "changed"): void;
}>();

const { tm } = useModuleI18n("features/analysis");
const { t } = useI18n();

const localScenarios = computed(() => props.scenarios);
const editing = ref<AnalysisScenario | null>(props.scenarios[0] ?? null);
const saving = ref(false);
const form = reactive({
  name: "",
  icon: "",
  description: "",
  instruction: "",
});
const isNew = ref(false);

function fillForm(scenario: AnalysisScenario | null) {
  form.name = scenario?.name ?? "";
  form.icon = scenario?.icon ?? "✏️";
  form.description = scenario?.description ?? "";
  form.instruction = scenario?.instruction ?? "";
}

function pick(scenario: AnalysisScenario) {
  isNew.value = false;
  editing.value = scenario;
  fillForm(scenario);
}

function startNew() {
  isNew.value = true;
  editing.value = null;
  fillForm(null);
}

watch(
  () => props.modelValue,
  (open) => {
    if (open && !editing.value) pick(props.scenarios[0]);
  },
);

async function save() {
  saving.value = true;
  try {
    if (isNew.value) {
      const res = await analysisApi.createScenario({
        name: form.name,
        icon: form.icon,
        description: form.description,
        instruction: form.instruction,
      });
      editing.value = res.data?.data ?? null;
      isNew.value = false;
    } else if (editing.value) {
      await analysisApi.updateScenario(editing.value.id, { ...form });
    }
    emit("changed");
  } catch (error: any) {
    console.error("Failed to save scenario:", error);
    alert(error?.response?.data?.message || String(error));
  } finally {
    saving.value = false;
  }
}

async function restore() {
  if (!editing.value) return;
  saving.value = true;
  try {
    const res = await analysisApi.restoreScenario(editing.value.id);
    editing.value = res.data?.data ?? editing.value;
    fillForm(editing.value);
    emit("changed");
  } catch (error: any) {
    console.error("Failed to restore scenario:", error);
    alert(error?.response?.data?.message || String(error));
  } finally {
    saving.value = false;
  }
}

async function remove() {
  if (!editing.value) return;
  saving.value = true;
  try {
    await analysisApi.deleteScenario(editing.value.id);
    editing.value = null;
    isNew.value = false;
    emit("changed");
  } catch (error: any) {
    console.error("Failed to delete scenario:", error);
    alert(error?.response?.data?.message || String(error));
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.dialog-title {
  font-size: 16px !important;
  font-weight: 600;
}
.dialog-subtitle {
  font-size: 12px;
  font-weight: 400;
  color: rgba(var(--v-theme-on-surface), 0.6);
  margin-top: 4px;
}
.chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}
.chip {
  padding: 6px 14px;
  border-radius: 18px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  font-size: 12.5px;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.chip.on {
  border-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.1);
}
.builtin-tag {
  font-size: 10px;
  color: rgb(var(--v-theme-success));
  margin-left: 4px;
}
.new-chip {
  border-style: dashed;
}
.field {
  margin-bottom: 14px;
}
.field-row {
  display: flex;
  gap: 12px;
}
.field-grow {
  flex: 1;
}
.f-label {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  margin-bottom: 6px;
}
.text-input {
  background: rgba(var(--v-theme-on-surface), 0.06);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  border-radius: 8px;
  color: rgb(var(--v-theme-on-surface));
  padding: 8px 12px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
  width: 100%;
}
.icon-input {
  width: 70px;
}
.text-input:focus {
  border-color: rgb(var(--v-theme-primary));
}
.instruction-area {
  background: rgba(var(--v-theme-on-surface), 0.06);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  border-radius: 8px;
  color: rgb(var(--v-theme-on-surface));
  padding: 12px;
  font-family: Consolas, Monaco, monospace;
  font-size: 12.3px;
  line-height: 1.7;
  resize: vertical;
  outline: none;
  width: 100%;
}
.instruction-area:focus {
  border-color: rgb(var(--v-theme-primary));
}
</style>
