import unittest

from app.validation import validate_report


class OptionalNewsURLTests(unittest.TestCase):
    def test_news_without_url_produces_warning_instead_of_crashing(self):
        report = '\n'.join([
            '# 研发技术日报 - 2026-10-21',
            '## 一、今日代码进展（Git 状态）',
            '## 二、AI 与自动驾驶行业动态',
            '## 三、团队建议跟进',
            '## 四、风险与明日建议',
        ])
        for url in (None, ''):
            with self.subTest(url=url):
                news = {'news_id': 'missing-source', 'source_name': 'Feed', 'url': url}
                result = validate_report(report, {'news_records': [news]}, {'valid_commits': []}, {'relevant_news': [news]})
                self.assertTrue(result['passed'])
                self.assertTrue(any('missing-source' in warning for warning in result['warnings']))
