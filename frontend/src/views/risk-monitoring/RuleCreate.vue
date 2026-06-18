<template>
  <div class="rule-create">
    <el-card shadow="never" class="create-card">
      <template #header>
        <div class="create-header">
          <div>
            <h3>
              <el-icon :size="20"><Plus /></el-icon>
              {{ isEdit ? '编辑规则' : '创建风险规则' }}
            </h3>
            <p class="create-desc">{{ isEdit ? '修改规则字段后保存' : '人工录入风险监控规则，填写业务场景并编写监控 SQL' }}</p>
          </div>
          <el-radio-group v-model="mode" v-if="!isEdit" size="small">
            <el-radio-button value="manual">人工录入</el-radio-button>
            <el-radio-button value="ai">AI 生成</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <!-- 人工录入模式 -->
      <el-form v-if="mode === 'manual'" ref="formRef" :model="form" :rules="rules" label-width="110px" label-position="right">
        <!-- 业务信息 -->
        <div class="form-section">
          <div class="form-section-title">业务信息</div>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="事业部" prop="business_unit">
                <el-select v-model="form.business_unit" placeholder="请选择" style="width: 100%" clearable>
                  <el-option label="科沃斯" value="ecovacs" />
                  <el-option label="添可" value="tineco" />
                  <el-option label="集团" value="group" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="渠道">
                <el-input v-model="form.channel" placeholder="如：线上/线下/经销商" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="业态">
                <el-select v-model="form.format" placeholder="请选择" style="width: 100%" clearable>
                  <el-option label="线上" value="online" />
                  <el-option label="线下" value="offline" />
                  <el-option label="新零售" value="new_retail" />
                  <el-option label="混合" value="mixed" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="业务循环">
                <el-input v-model="form.business_cycle" placeholder="如：采购付款循环" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="部门">
                <el-input v-model="form.department" placeholder="如：采购部" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="岗位">
                <el-input v-model="form.position" placeholder="如：采购经理" />
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <!-- 风险场景 -->
        <div class="form-section">
          <div class="form-section-title">风险场景定义</div>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="一级场景">
                <el-input v-model="form.level1_scene" placeholder="如：采购舞弊风险" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="二级场景">
                <el-input v-model="form.level2_scene" placeholder="如：供应商围标串标" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="三级场景" prop="level3_scene">
                <el-input v-model="form.level3_scene" placeholder="如：同一IP多供应商投标" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="人员信息">
            <el-input v-model="form.personnel_info" type="textarea" :rows="2" placeholder="涉及人员特征描述（选填）" />
          </el-form-item>
        </div>

        <!-- SQL 监控规则 -->
        <div class="form-section">
          <div class="form-section-title">SQL 监控规则</div>
          <el-form-item label="SQL 语句" prop="sql_statement">
            <el-input
              v-model="form.sql_statement"
              type="textarea"
              :rows="8"
              placeholder="请输入监控 SQL 语句，仅限只读查询（SELECT）"
              class="sql-editor"
            />
          </el-form-item>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="风险等级" prop="risk_level">
                <el-select v-model="form.risk_level" style="width: 100%">
                  <el-option label="高风险" value="高" />
                  <el-option label="中风险" value="中" />
                  <el-option label="低风险" value="低" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="阈值">
                <el-input-number v-model="form.threshold" :min="0" :precision="4" placeholder="金额/数量阈值" style="width: 100%" controls-position="right" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="监控频率" prop="monitor_frequency">
                <el-select v-model="form.monitor_frequency" style="width: 100%">
                  <el-option label="每天" value="daily" />
                  <el-option label="每周" value="weekly" />
                  <el-option label="每月" value="monthly" />
                  <el-option label="实时" value="realtime" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="监控事业部">
                <el-select v-model="form.monitor_business_unit" placeholder="请选择" style="width: 100%" clearable>
                  <el-option label="科沃斯" value="ecovacs" />
                  <el-option label="添可" value="tineco" />
                  <el-option label="集团" value="group" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="使用外部数据">
                <el-switch v-model="form.use_external_data" />
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <el-divider />
        <div class="form-actions">
          <el-button type="primary" :loading="loading" size="large" :icon="Check" @click="handleSubmit">
            {{ isEdit ? '保存修改' : '创建规则' }}
          </el-button>
          <el-button size="large" @click="$router.back()">取消</el-button>
        </div>
      </el-form>

      <!-- AI 生成模式 -->
      <div v-else class="ai-mode">
        <el-empty description="AI 生成功能即将上线，请使用人工录入模式">
          <template #image>
            <el-icon :size="64" color="#C0C4CC"><Cpu /></el-icon>
          </template>
          <el-button type="primary" @click="mode = 'manual'">切换到人工录入</el-button>
        </el-empty>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check } from '@element-plus/icons-vue'
import { riskMonitorApi } from '@/api'
import type { FormInstance, FormRules } from 'element-plus'

const route = useRoute()
const router = useRouter()
const formRef = ref<FormInstance>()
const loading = ref(false)
const mode = ref<'manual' | 'ai'>('manual')
const isEdit = ref(false)
const editId = ref<string | null>(null)

const form = reactive({
  business_unit: '',
  channel: '',
  format: '',
  department: '',
  position: '',
  personnel_info: '',
  business_cycle: '',
  level1_scene: '',
  level2_scene: '',
  level3_scene: '',
  sql_statement: '',
  risk_level: '中',
  threshold: null as number | null,
  monitor_frequency: 'daily',
  monitor_business_unit: '',
  use_external_data: false,
})

const rules: FormRules = {
  level3_scene: [{ required: true, message: '请输入三级场景', trigger: 'blur' }],
  sql_statement: [{ required: true, message: '请输入 SQL 语句', trigger: 'blur' }],
  risk_level: [{ required: true, message: '请选择风险等级', trigger: 'change' }],
  monitor_frequency: [{ required: true, message: '请选择监控频率', trigger: 'change' }],
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    const data: Record<string, unknown> = {
      business_unit: form.business_unit || undefined,
      channel: form.channel || undefined,
      format: form.format || undefined,
      department: form.department || undefined,
      position: form.position || undefined,
      personnel_info: form.personnel_info || undefined,
      business_cycle: form.business_cycle || undefined,
      level1_scene: form.level1_scene || undefined,
      level2_scene: form.level2_scene || undefined,
      level3_scene: form.level3_scene,
      sql_statement: form.sql_statement,
      risk_level: form.risk_level,
      threshold: form.threshold ?? undefined,
      monitor_frequency: form.monitor_frequency,
      monitor_business_unit: form.monitor_business_unit || undefined,
      use_external_data: form.use_external_data,
    }
    if (isEdit.value && editId.value) {
      await riskMonitorApi.rules.update(editId.value, data)
      ElMessage.success('规则已更新')
    } else {
      await riskMonitorApi.rules.create(data)
      ElMessage.success('规则创建成功，请提交审核')
    }
    router.push('/risk-monitor/rules')
  } catch {
    ElMessage.error(isEdit.value ? '更新规则失败' : '创建规则失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  const id = route.query.id as string
  if (id) {
    isEdit.value = true
    editId.value = id
    // TODO: 加载已有规则数据填充表单
    riskMonitorApi.rules.get(id).then((res) => {
      const r = res.data.rule
      Object.assign(form, {
        business_unit: r.business_unit || '',
        channel: r.channel || '',
        format: r.format || '',
        department: r.department || '',
        position: r.position || '',
        personnel_info: r.personnel_info || '',
        business_cycle: r.business_cycle || '',
        level1_scene: r.level1_scene || '',
        level2_scene: r.level2_scene || '',
        level3_scene: r.level3_scene,
        sql_statement: r.sql_statement,
        risk_level: r.risk_level,
        threshold: r.threshold ?? null,
        monitor_frequency: r.monitor_frequency,
        monitor_business_unit: r.monitor_business_unit || '',
        use_external_data: r.use_external_data,
      })
    }).catch(() => ElMessage.error('加载规则数据失败'))
  }
})
</script>

<style scoped>
.rule-create { max-width: 960px; margin: 0 auto; }
.create-card { border-radius: 10px; }
.create-header { display: flex; justify-content: space-between; align-items: center; }
.create-header h3 { margin: 0; display: flex; align-items: center; gap: 8px; }
.create-desc { margin: 4px 0 0 0; color: #909399; font-size: 13px; }

.form-section { margin-bottom: 8px; }
.form-section-title { font-size: 15px; font-weight: 600; color: #303133; margin-bottom: 16px; padding-left: 12px; border-left: 3px solid #E6A23C; }

.sql-editor :deep(textarea) { font-family: 'Cascadia Code', 'SF Mono', monospace; font-size: 13px; }

.form-actions { display: flex; justify-content: center; gap: 12px; padding-bottom: 8px; }

.ai-mode { padding: 60px 0; }
</style>
