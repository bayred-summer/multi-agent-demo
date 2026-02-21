version: 1

你上一条输出没有通过 JSON Schema 校验：{{validation_errors}}
请在不改变任务目标的前提下输出一个合法 JSON 对象。
禁止输出任何 JSON 之外文本；首字符必须是 {，末字符必须是 }。

上一条原始输出如下，请仅转换为合法 JSON：
{{previous_output}}

请严格匹配以下 schema：
{{schema}}
