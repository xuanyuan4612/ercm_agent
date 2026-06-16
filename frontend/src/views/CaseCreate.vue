<template>
  <div class="case-create">
    <el-card shadow="never" class="create-card">
      <template #header>
        <div class="create-header">
          <div>
            <h3 style="margin: 0">
              <el-icon :size="20"><Plus /></el-icon>
              创建廉洁监察案件
            </h3>
            <p class="create-desc">填写案件基本信息后将启动 AI 辅助调查流程</p>
          </div>
        </div>
      </template>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="120px"
        label-position="right"
        class="create-form"
      >
        <!-- 基本信息 -->
        <div class="form-section">
          <div class="form-section-title">基本信息</div>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="事业部" prop="client">
                <el-select v-model="form.client" placeholder="请选择事业部" style="width: 100%">
                  <el-option label="科沃斯" value="ecovacs" />
                  <el-option label="添可" value="tineco" />
                  <el-option label="集团" value="group" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="案件来源" prop="fraud_source">
                <el-select v-model="form.fraud_source" placeholder="请选择来源" style="width: 100%">
                  <el-option label="手动录入" value="manual" />
                  <el-option label="公众号举报" value="wechat" />
                  <el-option label="邮箱举报" value="email" />
                  <el-option label="电话举报" value="phone" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <!-- 案件详情 -->
        <div class="form-section">
          <div class="form-section-title">案件详情</div>
          <el-form-item label="舞弊事件" prop="fraud_event_detail">
            <el-input
              v-model="form.fraud_event_detail"
              type="textarea"
              :rows="6"
              placeholder="请详细描述舞弊事件，包括时间、地点、涉及人员、行为方式等（至少10个字符）"
            />
          </el-form-item>
          <el-form-item label="证据简述">
            <el-input
              v-model="form.proof"
              type="textarea"
              :rows="3"
              placeholder="简述已有证据情况，如：财务单据、聊天记录、邮件等"
            />
          </el-form-item>
        </div>

        <!-- 涉及方 -->
        <div class="form-section">
          <div class="form-section-title">涉及方</div>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="涉及员工">
                <el-select
                  v-model="form.reported_staff_names"
                  multiple
                  filterable
                  allow-create
                  placeholder="输入姓名后回车添加"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="涉及供应商">
                <el-select
                  v-model="form.reported_supplier_names"
                  multiple
                  filterable
                  allow-create
                  placeholder="输入名称后回车添加"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="涉及经销商">
                <el-select
                  v-model="form.reported_dealer_names"
                  multiple
                  filterable
                  allow-create
                  placeholder="输入名称后回车添加"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <!-- 举报人信息 -->
        <div class="form-section">
          <div class="form-section-title">举报人信息（选填）</div>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="举报人电话">
                <el-input v-model="form.fraud_tel" placeholder="选填" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="举报人邮箱">
                <el-input v-model="form.fraud_email" placeholder="选填" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="风控案件ID">
                <el-input v-model="form.risk_control_case_id" placeholder="选填">
                  <template #suffix>
                    <el-tooltip content="当前风控系统尚未接入，为手动上传模式" placement="top">
                      <el-icon><QuestionFilled /></el-icon>
                    </el-tooltip>
                  </template>
                </el-input>
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <!-- 操作按钮 -->
        <el-divider />
        <div class="form-actions">
          <el-button type="primary" :loading="loading" size="large" :icon="Check" @click="handleCreate">
            创建案件
          </el-button>
          <el-button size="large" @click="$router.back()">取消</el-button>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, QuestionFilled } from '@element-plus/icons-vue'
import { casesApi } from '@/api'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const formRef = ref<FormInstance>()
const loading = ref(false)

const form = reactive({
  client: 'ecovacs',
  fraud_source: 'manual',
  fraud_event_detail: '',
  proof: '',
  reported_staff_names: [] as string[],
  reported_supplier_names: [] as string[],
  reported_dealer_names: [] as string[],
  fraud_tel: '',
  fraud_email: '',
  fraud_other_info: '',
  risk_control_case_id: '',
})

const rules: FormRules = {
  client: [{ required: true, message: '请选择事业部', trigger: 'change' }],
  fraud_source: [{ required: true, message: '请选择案件来源', trigger: 'change' }],
  fraud_event_detail: [{ required: true, min: 10, message: '事件详情至少10个字符', trigger: 'blur' }],
}

async function handleCreate() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await casesApi.create({ ...form })
    ElMessage.success('案件创建成功')
    router.push('/cases')
  } catch {
    ElMessage.error('创建案件失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.case-create { max-width: 900px; margin: 0 auto; }
.create-card { border-radius: 10px; }
.create-header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
}
.create-desc {
  margin: 4px 0 0 0;
  color: #909399;
  font-size: 13px;
}
.create-form { margin-top: 8px; }

.form-section { margin-bottom: 8px; }
.form-section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 16px;
  padding-left: 12px;
  border-left: 3px solid #409EFF;
}

.form-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  padding-bottom: 8px;
}
</style>
