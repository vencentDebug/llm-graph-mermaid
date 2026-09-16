/**
 * LLM 客户端
 * 调用 Claude API 生成 GraphJSON
 */

import Anthropic from '@anthropic-ai/sdk';
import { GraphJSON, GraphJSONSchema } from '../types/graph';
import { generateGraphPrompt } from './prompt';

const client = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
});

/**
 * 调用 LLM 生成 GraphJSON
 * @param userInput 用户的自然语言描述
 * @param type 流程类型：general | workflow | architecture | pipeline
 * @returns 生成的 GraphJSON
 * @throws 如果 LLM 输出无效或 JSON 解析失败
 */
export async function generateGraphJSON(
  userInput: string,
  type: 'general' | 'workflow' | 'architecture' | 'pipeline' = 'general'
): Promise<GraphJSON> {
  try {
    const prompt = generateGraphPrompt(userInput, type);

    const message = await client.messages.create({
      model: 'claude-3-5-sonnet-20241022',
      max_tokens: 2048,
      messages: [
        {
          role: 'user',
          content: prompt,
        },
      ],
    });

    // 提取文本内容
    const content = message.content
      .filter((block) => block.type === 'text')
      .map((block) => (block.type === 'text' ? block.text : ''))
      .join('\n');

    if (!content) {
      throw new Error('LLM 返回了空内容');
    }

    // 清理可能的 markdown 格式
    const cleanedContent = content
      .replace(/```json\n?/g, '')
      .replace(/```\n?/g, '')
      .trim();

    // 解析 JSON
    let graphJson: any;
    try {
      graphJson = JSON.parse(cleanedContent);
    } catch (parseError) {
      console.error('JSON 解析错误:', cleanedContent);
      throw new Error(`无法解析 LLM 返回的 JSON: ${parseError}`);
    }

    // 验证格式
    const validated = GraphJSONSchema.parse(graphJson);
    return validated;
  } catch (error) {
    if (error instanceof Error) {
      throw new Error(`生成 GraphJSON 失败: ${error.message}`);
    }
    throw error;
  }
}

/**
 * 流式生成 GraphJSON（用于长流程）
 * @param userInput 用户的自然语言描述
 * @param type 流程类型
 * @param onChunk 接收到数据块时的回调
 */
export async function* generateGraphJSONStream(
  userInput: string,
  type: 'general' | 'workflow' | 'architecture' | 'pipeline' = 'general',
  onChunk?: (chunk: string) => void
) {
  const prompt = generateGraphPrompt(userInput, type);

  const stream = await client.messages.stream({
    model: 'claude-3-5-sonnet-20241022',
    max_tokens: 2048,
    messages: [
      {
        role: 'user',
        content: prompt,
      },
    ],
  });

  let fullContent = '';

  for await (const chunk of stream) {
    if (
      chunk.type === 'content_block_delta' &&
      chunk.delta.type === 'text_delta'
    ) {
      const text = chunk.delta.text;
      fullContent += text;
      if (onChunk) {
        onChunk(text);
      }
      yield text;
    }
  }

  // 返回完整的 GraphJSON
  const cleanedContent = fullContent
    .replace(/```json\n?/g, '')
    .replace(/```\n?/g, '')
    .trim();

  try {
    const graphJson = JSON.parse(cleanedContent);
    const validated = GraphJSONSchema.parse(graphJson);
    return validated;
  } catch (error) {
    throw new Error(`最终 JSON 验证失败: ${error}`);
  }
}

/**
 * 优化现有的 GraphJSON（添加更多细节或调整）
 * @param graphJson 现有的 GraphJSON
 * @param improvements 改进要求
 * @returns 改进后的 GraphJSON
 */
export async function optimizeGraphJSON(
  graphJson: GraphJSON,
  improvements: string
): Promise<GraphJSON> {
  const prompt = `
以下是现有的 GraphJSON：

${JSON.stringify(graphJson, null, 2)}

请根据以下要求进行改进：
${improvements}

返回改进后的 GraphJSON（仅返回 JSON，不要其他文本）：
`;

  const message = await client.messages.create({
    model: 'claude-3-5-sonnet-20241022',
    max_tokens: 2048,
    messages: [
      {
        role: 'user',
        content: prompt,
      },
    ],
  });

  const content = message.content
    .filter((block) => block.type === 'text')
    .map((block) => (block.type === 'text' ? block.text : ''))
    .join('\n');

  const cleanedContent = content
    .replace(/```json\n?/g, '')
    .replace(/```\n?/g, '')
    .trim();

  const optimized = JSON.parse(cleanedContent);
  return GraphJSONSchema.parse(optimized);
}
