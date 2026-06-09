<template>
  <div class="case-create">
    <el-card>
      <template #header><h3 style="margin: 0">创建廉洁监察案件</h3></template>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px" style="max-width: 800px">
        <el-form-item label="事业部" prop="client">
          <el-select v-model="form.client" placeholder="请选择事业部">
            <el-option label="科沃斯" value="ecovacs" />
            <el-option label="添可" value="tineco" />
            <el-option label="集团" value="group" />
          </el-select>
        </el-form-item>
        <el-form-item label="案件来源" prop="fraud_source">
          <el-select v-model="form.fraud_source" placeholder="请选择来源">
            <el-option label="手动录入" value="manual" />
            <el-option label="公众号举报" value="wechat" />
            <el-option label="邮箱举报" value="email" />
            <el-option label="电话举报" value="phone" />
          </el-select>
        </el-form-item>
        <el-form-item label="舞弊事件详情" prop="fraud_event_detail">
          <el-input v-model="form.fraud_event_detail" type="textarea" :rows="6" placeholder="请详细描述舞弊事件（至少10个字符）" />
        </el-form-item>
        <el-form-item label="证据简述" prop="proof">
          <el-input v-model="form.proof" type="textarea" :rows="3" placeholder="简述已有证据情况" />
        </el-form-item>
        <el-form-item label="涉及员工">
          <el-select v-model="form.reported_staff_names" multiple filterable allow-create placeholder="输入员工姓名后回车添加" style="width: 100%" />
        </el-form-item>
        <el-form-item label="涉及供应商">
          <el-select v-model="form.reported_supplier_names" multiple filterable allow-create placeholder="输入供应商名称后回车添加" style="width: 100%" />
        </el-form-item>
        <el-form-item label="涉及经销商">
          <el-select v-model="form.reported_dealer_names" multiple filterable allow-create placeholder="输入经销商名称后回车添加" style="width: 100%" />
        </el-form-item>
        <el-form-item label="举报人电话">
          <el-input v-model="form.fraud_tel" placeholder="选填" />
        </el-form-item>
        <el-form-item label="举报人邮箱">
          <el-input v-model="form.fraud_email" placeholder="选填" />
        </el-form-item>
        <el-form-item label="风控案件ID">
          <el-input v-model="form.risk_control_case_id" placeholder="选填（风控系统关联案件ID）" />
          <div style="color: #909399; font-size: 12px; margin-top: 4px">
            当前风控系统尚未接入，为手动上传模式
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleCreate">创建案件</el-button>
          <el-button @click="$router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
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
    const payload = { ...form }
    await casesApi.create(payload)
    ElMessage.success('案件创建成功')
    router.push('/cases')
  } catch {
    ElMessage.error('创建案件失败')
  } finally {
    loading.value = false
  }
}
</script>
