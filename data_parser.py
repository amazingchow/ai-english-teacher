import re
import ast
from typing import Dict, Any, List

def parse_data_line(line: str) -> Dict[str, Any]:
    """
    解析单行数据，将其转换为字典格式
    
    Args:
        line: 输入的数据行字符串
        
    Returns:
        解析后的字典
    """
    result = {}
    
    # 使用正则表达式分割字段，但保持嵌套结构
    # 匹配 pattern: field_name=value
    pattern = r'(\w+)=([^=]+?)(?=\s+\w+=|$)'
    matches = re.findall(pattern, line)
    
    for field_name, field_value in matches:
        # 清理字段值（去除首尾空格）
        field_value = field_value.strip()
        
        # 处理不同的值类型
        if field_value == 'None':
            result[field_name] = None
        elif field_value == 'True':
            result[field_name] = True
        elif field_value == 'False':
            result[field_name] = False
        elif field_value.startswith('"') and field_value.endswith('"'):
            # 字符串值
            result[field_name] = field_value[1:-1]
        elif field_value.startswith("'") and field_value.endswith("'"):
            # 字符串值
            result[field_name] = field_value[1:-1]
        elif field_value.startswith('<') and field_value.endswith('>'):
            # 枚举值，如 <MediaModality.TEXT: 'TEXT'>
            result[field_name] = field_value
        elif field_value.startswith('[') and field_value.endswith(']'):
            # 列表值，尝试解析
            try:
                # 对于简单的列表，尝试用ast.literal_eval解析
                result[field_name] = ast.literal_eval(field_value)
            except:
                # 如果解析失败，保持原始字符串
                result[field_name] = field_value
        elif field_value.startswith('Content(') or field_value.startswith('LiveServerContent(') or field_value.startswith('Part(') or field_value.startswith('UsageMetadata(') or field_value.startswith('ModalityTokenCount('):
            # 复杂对象，保持原始字符串
            result[field_name] = field_value
        else:
            # 尝试解析为数字
            try:
                if '.' in field_value:
                    result[field_name] = float(field_value)
                else:
                    result[field_name] = int(field_value)
            except ValueError:
                # 如果都不是，保持原始字符串
                result[field_name] = field_value
    
    return result

def parse_data_file(file_path: str) -> List[Dict[str, Any]]:
    """
    解析整个数据文件
    
    Args:
        file_path: 数据文件路径
        
    Returns:
        包含所有解析后数据的列表
    """
    parsed_data = []
    
    with open(file_path, 'r', encoding='utf-8') as file:
        for line_num, line in enumerate(file, 1):
            line = line.strip()
            if line:  # 跳过空行
                try:
                    parsed_line = parse_data_line(line)
                    parsed_line['_line_number'] = line_num  # 添加行号用于调试
                    parsed_data.append(parsed_line)
                except Exception as e:
                    print(f"解析第 {line_num} 行时出错: {e}")
                    print(f"问题行: {line}")
    
    return parsed_data

def extract_text_content(parsed_data: List[Dict[str, Any]]) -> List[str]:
    """
    从解析的数据中提取文本内容
    
    Args:
        parsed_data: 解析后的数据列表
        
    Returns:
        提取的文本内容列表
    """
    texts = []
    
    for item in parsed_data:
        if 'server_content' in item:
            server_content = item['server_content']
            # 查找包含文本的部分
            if 'text=' in server_content:
                # 使用正则表达式提取text字段的值
                text_match = re.search(r"text='([^']*)'", server_content)
                if text_match:
                    texts.append(text_match.group(1))
    
    return texts

# 示例使用
if __name__ == "__main__":
    # 解析数据文件
    data = parse_data_file('data')
    
    print("解析后的数据:")
    for i, item in enumerate(data):
        print(f"\n--- 第 {i+1} 行 ---")
        for key, value in item.items():
            if key != '_line_number':
                print(f"{key}: {value}")
    
    print("\n" + "="*50)
    print("提取的文本内容:")
    texts = extract_text_content(data)
    for i, text in enumerate(texts):
        print(f"{i+1}. {text}") 