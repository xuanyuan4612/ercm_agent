<template>
  <div class="admin-view">
    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card stat-card--users">
        <div class="stat-card-icon">
          <el-icon :size="22"><UserFilled /></el-icon>
        </div>
        <div class="stat-card-body">
          <span class="stat-card-num">{{ userTotal }}</span>
          <span class="stat-card-label">注册用户</span>
        </div>
      </div>
      <div class="stat-card stat-card--audit">
        <div class="stat-card-icon">
          <el-icon :size="22"><Monitor /></el-icon>
        </div>
        <div class="stat-card-body">
          <span class="stat-card-num">{{ auditTotal }}</span>
          <span class="stat-card-label">审计日志</span>
        </div>
      </div>
    </div>

    <!-- 标签页 -->
    <el-card class="admin-tabs-card" shadow="never">
      <el-tabs v-model="activeTab">
        <!-- 用户管理 -->
        <el-tab-pane label="用户管理" name="users">
          <template #label>
            <span class="tab-label">
              <el-icon :size="16"><User /></el-icon>
              用户管理
            </span>
          </template>
          <div class="tab-toolbar">
            <span class="toolbar-info">共 {{ userTotal }} 人</span>
            <el-button type="primary" size="small" :icon="Plus" @click="showCreateDialog = true">
              创建用户
            </el-button>
          </div>

          <el-table :data="users" v-loading="userLoading" stripe highlight-current-row>
            <el-table-column prop="username" label="用户名" width="120" />
            <el-table-column prop="display_name" label="姓名" width="100" />
            <el-table-column prop="department" label="部门" width="140" />
            <el-table-column prop="email" label="邮箱" min-width="180" />
            <el-table-column label="角色" width="110">
              <template #default="{ row }">
                <el-tag
                  :type="row.role === 'group' ? 'danger' : row.role === 'tineco' ? 'warning' : 'success'"
                  size="small"
                  effect="light"
                >
                  {{ roleLabel(row.role) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small" effect="light">
                  {{ row.is_active ? '启用' : '禁用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="last_login" label="最后登录" width="180" />
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button size="small" :type="row.is_active ? 'warning' : 'success'" link @click="toggleUser(row)">
                  {{ row.is_active ? '禁用' : '启用' }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="userPage"
              :page-size="20"
              :total="userTotal"
              layout="total, prev, pager, next"
              @current-change="fetchUsers"
            />
          </div>
        </el-tab-pane>

        <!-- 审计日志 -->
        <el-tab-pane label="审计日志" name="audit">
          <template #label>
            <span class="tab-label">
              <el-icon :size="16"><Monitor /></el-icon>
              审计日志
            </span>
          </template>
          <div class="tab-toolbar">
            <span class="toolbar-info">共 {{ auditTotal }} 条记录</span>
          </div>

          <el-table :data="auditLogs" v-loading="auditLoading" stripe empty-text="暂无审计日志" highlight-current-row>
            <el-table-column prop="operator_id" label="操作人" width="120" />
            <el-table-column label="操作" width="130">
              <template #default="{ row }">
                <el-tag size="small" effect="light">{{ row.operation }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="target_table" label="目标表" width="130" />
            <el-table-column prop="target_id" label="目标ID" min-width="200" />
            <el-table-column prop="ip_address" label="IP地址" width="150" />
            <el-table-column prop="created_at" label="时间" width="190" />
          </el-table>

          <div class="pagination-wrapper">
            <el-pagination
              v-model:current-page="auditPage"
              :page-size="20"
              :total="auditTotal"
              layout="total, prev, pager, next"
              @current-change="fetchAuditLogs"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 创建用户对话框 -->
    <el-dialog v-model="showCreateDialog" title="创建用户" width="500px" draggable>
      <el-form :model="newUser" label-width="100px" label-position="right">
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { adminApi } from '@/api'
import type { UserInfo } from '@/types'

const activeTab = ref('users')

// ── 用户管理 ──
const users = ref<UserInfo[]>([])
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
    users.value = (res.data.items || []) as unknown as UserInfo[]
    userTotal.value = res.data.total
  } finally {
    userLoading.value = false
  }
}

async function toggleUser(row: UserInfo) {
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

<style scoped>
.admin-view { max-width: 1200px; margin: 0 auto; }

/* ── 统计卡片 ── */
.stats-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.stat-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid #EBEEF5;
  transition: all 0.2s ease;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
.stat-card-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-card--users .stat-card-icon { background: #409EFF15; color: #409EFF; }
.stat-card--audit .stat-card-icon { background: #67C23A15; color: #67C23A; }
.stat-card-body { display: flex; flex-direction: column; }
.stat-card-num { font-size: 24px; font-weight: 700; color: #303133; line-height: 1.2; }
.stat-card-label { font-size: 13px; color: #909399; margin-top: 2px; }

/* ── 标签页 ── */
.admin-tabs-card { border-radius: 8px; }
.tab-label { display: flex; align-items: center; gap: 6px; }
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar-info { color: #909399; font-size: 13px; }

.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: center;
}
</style>
