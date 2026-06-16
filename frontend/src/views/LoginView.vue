<template>
  <div class="login-container">
    <div class="login-bg-shapes">
      <div class="shape shape-1"></div>
      <div class="shape shape-2"></div>
      <div class="shape shape-3"></div>
    </div>
    <el-card class="login-card" shadow="always">
      <template #header>
        <div class="login-header">
          <div class="login-logo">🔱</div>
          <h2>赫尔墨斯（Hermes）</h2>
          <p>风控 AI 智能体系统</p>
        </div>
      </template>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="handleLogin"
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            :prefix-icon="User"
            size="large"
            @keyup.enter="focusPassword"
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            ref="passwordRef"
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            show-password
            :prefix-icon="Lock"
            size="large"
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            native-type="submit"
            :loading="loading"
            size="large"
            style="width: 100%"
          >
            {{ loading ? '登录中...' : '登 录' }}
          </el-button>
        </el-form-item>
      </el-form>
      <div class="login-footer">
        <span>© 2025 赫尔墨斯风控平台</span>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref<FormInstance>()
const passwordRef = ref()
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

function focusPassword() {
  passwordRef.value?.focus()
}

async function handleLogin() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await authStore.login({ username: form.username, password: form.password })
    ElMessage.success('登录成功')
    router.push('/')
  } catch {
    ElMessage.error('登录失败，请检查用户名和密码')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 40%, #0f3460 100%);
  position: relative;
  overflow: hidden;
}

/* ── 背景装饰图形 ── */
.login-bg-shapes {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}
.shape {
  position: absolute;
  border-radius: 50%;
  opacity: 0.06;
  background: #fff;
}
.shape-1 {
  width: 600px;
  height: 600px;
  top: -200px;
  right: -150px;
  animation: float 20s ease-in-out infinite;
}
.shape-2 {
  width: 400px;
  height: 400px;
  bottom: -100px;
  left: -100px;
  animation: float 15s ease-in-out infinite reverse;
}
.shape-3 {
  width: 300px;
  height: 300px;
  top: 40%;
  left: 20%;
  animation: float 18s ease-in-out infinite 5s;
}
@keyframes float {
  0%, 100% { transform: translate(0, 0) rotate(0deg); }
  33% { transform: translate(30px, -30px) rotate(10deg); }
  66% { transform: translate(-20px, 20px) rotate(-5deg); }
}

.login-card {
  width: 420px;
  border-radius: 12px;
  border: none;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  position: relative;
  z-index: 1;
}

.login-header {
  text-align: center;
  padding: 8px 0;
}
.login-logo {
  font-size: 48px;
  margin-bottom: 8px;
}
.login-header h2 {
  margin: 0 0 8px 0;
  color: #303133;
  font-size: 22px;
  font-weight: 700;
}
.login-header p {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.login-footer {
  text-align: center;
  color: #C0C4CC;
  font-size: 12px;
  margin-top: 8px;
}
</style>
