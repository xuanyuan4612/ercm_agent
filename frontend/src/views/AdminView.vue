<template>
  <div class="admin-view">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="用户管理" name="users">
        <el-card>
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>用户列表（共 {{ userTotal }} 人）</span>
              <el-button type="primary" size="small" @click="showCreateDialog = true">
                <el-icon><Plus /></el-icon> 创建用户
              </el-button>
            </div>
          </template>
          <el-table :data="users" v-loading="userLoading" stripe>
            <el-table-column prop="username" label="用户名" width="120" />
            <el-table-column prop="display_name" label="姓名" width="100" />
            <el-table-column prop="department" label="部门" width="120" />
            <el-table-column prop="email" label="邮箱" width="180" />
            <el-table-column label="角色" width="100">
              <template #default="{ row }">
                <el-tag :type="row.role === 'group' ? 'danger' : row.role === 'tineco' ? 'warning' : 'success'" size="small">
                  {{ roleLabel(row.role) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                  {{ row.is_active ? '启用' : '禁用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="last_login" label="最后登录" width="180" />
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button size="small" @click="toggleUser(row)">{{ row.is_active ? '禁用' : '启用' }}</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div style="margin-top: 16px; display: flex; justify-content: center">
            <el-pagination v-model:current-page="userPage" :page-size="20" :total="userTotal" layout="total, prev, pager, next" @current-change="fetchUsers" />
          </div>
        </el-card>

        <!-- 创建用户对话框 -->
        <el-dialog v-model="showCreateDialog" title="创建用户" width="500px">
          <el-form :model="newUser" label-width="100px">
            <el-form-item label="用户名" required>
              <el-input v-model="newUser.username" placeholder="3-50个字符" />
            </el-form-item>
            <el-form-item label="密码" required>
              <el-input v-model="newUser.password" type="password" placeholder="至少8个字符" show-password />
            </el-form-item>
            <el-form-item label="姓名" required>
              <el-input v-model="newUser.display_name" placeholder="员工真实姓名" />
            </el-form-item>
            <el-form-item label="部门" required>
              <el-input v-model="newUser.department" placeholder="所属部门" />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="newUser.email" placeholder="选填" />
            </el-form-item>
            <el-form-item label="角色" required>
              <el-select v-model="newUser.role" style="width: 100%">
                <el-option label="集团管理员" value="group" />
                <el-option label="科沃斯" value="ecovacs" />
                <el-option label="添可" value="tineco" />
              </el-select>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="showCreateDialog = false">取消</el-button>
            <el-button type="primary" :loading="creating" @click="createUser">创建</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <el-tab-pane label="审计日志" name="audit">
        <el-card>
          <el-table :data="auditLogs" v-loading="auditLoading" stripe empty-text="暂无审计日志">
            <el-table-column prop="operator_id" label="操作人" width="120" />
            <el-table-column prop="operation" label="操作" width="120" />
            <el-table-column prop="target_table" label="目标表" width="120" />
            <el-table-column prop="target_id" label="目标ID" width="200" />
            <el-table-column prop="ip_address" label="IP地址" width="140" />
            <el-table-column prop="created_at" label="时间" width="180" />
          </el-table>
          <div style="margin-top: 16px; display: flex; justify-content: center">
            <el-pagination v-model:current-page="auditPage" :page-size="20" :total="auditTotal" layout="total, prev, pager, next" @current-change="fetchAuditLogs" />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi } from '@/api'

const activeTab = ref('users')

// ── 用户管理 ──
const users = ref<Array<Record<string, unknown>>>([])
const userTotal = ref(0)
const userPage = ref(1)
const userLoading = ref(false)

function roleLabel(v: string) {
  const m: Record<string, string> = { group: '集团管理员', ecovacs: '科沃斯', tineco: '添可' }
  return m[v] || v
}

async function fetchUsers() {
  userLoading.value = true
  try {
    const res = await adminApi.users({ page: userPage.value, page_size: 20 })
    users.value = (res.data.items || []) as Array<Record<string, unknown>>
    userTotal.value = res.data.total
  } finally {
    userLoading.value = false
  }
}

async function toggleUser(row: Record<string, unknown>) {
  try {
    await adminApi.toggleUser(row.id as string)
    ElMessage.success('状态已更新')
    fetchUsers()
  } catch { ElMessage.error('操作失败') }
}

// ── 创建用户 ──
const showCreateDialog = ref(false)
const creating = ref(false)
const newUser = reactive({
  username: '', password: '', display_name: '', department: '', email: '', role: 'ecovacs',
})

async function createUser() {
  creating.value = true
  try {
    await adminApi.createUser({ ...newUser })
    ElMessage.success('用户创建成功')
    showCreateDialog.value = false
    Object.assign(newUser, { username: '', password: '', display_name: '', department: '', email: '', role: 'ecovacs' })
    fetchUsers()
  } catch { ElMessage.error('创建失败') }
  finally { creating.value = false }
}

// ── 审计日志 ──
const auditLogs = ref<Array<Record<string, unknown>>>([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditLoading = ref(false)

async function fetchAuditLogs() {
  auditLoading.value = true
  try {
    const res = await adminApi.auditLogs({ page: auditPage.value, page_size: 20 })
    auditLogs.value = (res.data.items || []) as Array<Record<string, unknown>>
    auditTotal.value = res.data.total
  } finally {
    auditLoading.value = false
  }
}

onMounted(() => { fetchUsers(); fetchAuditLogs() })
</script>
