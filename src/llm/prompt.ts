/**
 * LLM Prompt 模板
 * 用于指导大模型生成标准化的 GraphJSON 格式
 */

export const GRAPH_GENERATION_SYSTEM_PROMPT = `你是一个专业的流程图和系统架构设计师。
用户会用自然语言描述一个业务流程、系统架构或工作流程。
你需要生成一个标准的 GraphJSON 结构来表示这个流程。

重要规则：
1. 每个节点必须有唯一的 ID（如 n1, n2, n3...）
2. 节点类型包括：start（开始）、process（处理）、decision（决策）、end（结束）、subprocess（子流程）
3. 边连接节点，可以包含标签和条件
4. 决策节点的出边应该有清晰的条件标签（如"是"、"否"、"成功"、"失败"）
5. 返回必须是有效的 JSON，不要包含任何 markdown 标记
6. 确保流程有合理的开始和结束点

生成的 JSON 结构必须符合以下格式：
{
  "version": "1.0",
  "title": "流程名称",
  "description": "简要描述",
  "nodes": [
    {
      "id": "n1",
      "label": "节点标签",
      "type": "start|process|decision|end|subprocess",
      "description": "详细描述（可选）"
    }
  ],
  "edges": [
    {
      "from": "n1",
      "to": "n2",
      "label": "边的标签（可选）",
      "condition": "条件表达式（决策分支时使用）"
    }
  ]
}`;

export const GRAPH_GENERATION_USER_PROMPT = (userInput: string) => `
请根据以下描述生成 GraphJSON：

${userInput}

要求：
1. 识别主要的流程步骤和决策点
2. 合理使用节点类型（开始、处理、决策、结束）
3. 确保流程的逻辑完整性
4. 使用清晰的标签和条件说明
5. 只返回 JSON，不要有其他文本

生成的 GraphJSON：`;

/**
 * 针对特定场景的 prompt 模板
 */

export const WORKFLOW_PROMPT = (description: string) => `
生成一个工作流程图。流程描述如下：

${description}

请创建一个清晰的流程图，包含：
- 触发事件（start 节点）
- 主要的处理步骤（process 节点）
- 条件分支和决策点（decision 节点）
- 流程结束（end 节点）`;

export const ARCHITECTURE_PROMPT = (description: string) => `
生成一个系统架构图。系统描述如下：

${description}

请创建一个架构图，展示：
- 主要组件或服务（process/subprocess 节点）
- 组件间的交互和数据流（edges）
- 系统的输入输出（start/end 节点）
- 关键的架构决策或路由（decision 节点）`;

export const DATA_PIPELINE_PROMPT = (description: string) => `
生成一个数据处理管道图。管道描述如下：

${description}

请创建一个数据流图，展示：
- 数据源（start 节点）
- 数据处理步骤（process 节点）
- 数据验证和条件检查（decision 节点）
- 数据输出（end 节点）
- 数据在各步骤间的流向（edges）`;

/**
 * 生成 prompt 的辅助函数
 */

export function generateGraphPrompt(
  userInput: string,
  type: 'general' | 'workflow' | 'architecture' | 'pipeline' = 'general'
): string {
  const systemPrompt = GRAPH_GENERATION_SYSTEM_PROMPT;
  
  let userPrompt: string;
  
  switch (type) {
    case 'workflow':
      userPrompt = WORKFLOW_PROMPT(userInput);
      break;
    case 'architecture':
      userPrompt = ARCHITECTURE_PROMPT(userInput);
      break;
    case 'pipeline':
      userPrompt = DATA_PIPELINE_PROMPT(userInput);
      break;
    default:
      userPrompt = GRAPH_GENERATION_USER_PROMPT(userInput);
  }
  
  return `${systemPrompt}\n\n${userPrompt}`;
}
