from whoosh.analysis import Tokenizer, Token
import jieba # 确保 jieba 在这里也被导入

# --- 中文分词器和分析器 ---
class ChineseTokenizer(Tokenizer):
    def __call__(self, value, positions=True, chars=True, keeporiginal=False,
                 removestops=True, start_pos=0, start_char=0, mode='', **kw):
        assert isinstance(value, str)
        # 使用jieba进行分词
        seg_list = jieba.cut_for_search(value)
        current_pos = 0
        for token_text in seg_list:
            start_char_offset = value.find(token_text, current_pos)
            if start_char_offset == -1:  # Fallback if find fails (e.g. due to case changes by jieba)
                start_char_offset = current_pos

            token = Token()
            token.text = token_text
            token.pos = start_pos + current_pos  # Position in terms of tokens
            if positions:
                token.startchar = start_char + start_char_offset
                token.endchar = start_char + start_char_offset + len(token_text)
            yield token
            current_pos += len(token_text)


class ChineseAnalyzer:
    def __init__(self):
        self.tokenizer = ChineseTokenizer()

    def __call__(self, value, positions=True, chars=True, keeporiginal=False,
                 removestops=True, start_pos=0, start_char=0, mode='', **kw):
        # 返回分词结果的生成器
        return (token for token in self.tokenizer(value, positions=positions, chars=chars,
                                                  keeporiginal=keeporiginal, removestops=removestops,
                                                  start_pos=start_pos, start_char=start_char))
