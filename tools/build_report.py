"""从可编辑Markdown工程材料生成一份四章PDF参考稿。仅制报告需要reportlab。"""
import html
import json
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, PageBreak, PageTemplate,
                               Paragraph, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output' / 'pdf'
WIDTH = A4[0] - 100


def fonts():
    # 优先嵌入Windows中文字体，也可在其他机器提供同名字体路径。
    regular = Path('C:/Windows/Fonts/simsun.ttc')
    bold = Path('C:/Windows/Fonts/msyhbd.ttc')
    if not regular.exists() or not bold.exists():
        raise RuntimeError('生成报告需要中文字体：请在fonts()中指定本机宋体和黑体路径')
    pdfmetrics.registerFont(TTFont('Song', str(regular), subfontIndex=0))
    pdfmetrics.registerFont(TTFont('Hei', str(bold), subfontIndex=0))
    pdfmetrics.registerFontFamily('Song', normal='Song', bold='Hei', italic='Song', boldItalic='Hei')


class Report(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == 'Chapter':
            title = flowable.getPlainText()
            key = f'chapter-{self.page}'
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, 0)
            self.notify('TOCEntry', (0, title, self.page, key))


def page(canvas, doc):
    canvas.saveState()
    if doc.page > 1:
        canvas.setFont('Song', 8)
        canvas.drawString(50, A4[1] - 30, '大学生竞赛信息与组队管理系统  工程参考稿  待个人材料补齐')
        canvas.setStrokeColor(colors.HexColor('#D9D9D9'))
        canvas.line(50, A4[1] - 36, A4[0] - 50, A4[1] - 36)
        canvas.drawCentredString(A4[0] / 2, 25, str(doc.page))
    canvas.restoreState()


def architecture():
    d = Drawing(WIDTH, 260)
    def box(x, y, w, h, lines):
        d.add(Rect(x, y, w, h, strokeColor=colors.black, fillColor=colors.white, strokeWidth=.7))
        for index, text in enumerate(lines):
            d.add(String(x + w / 2, y + h / 2 + (len(lines) - 1) * 6 - index * 12 - 3,
                         text, fontName='Song', fontSize=10, textAnchor='middle'))
    def arrow(x1, y1, x2, y2):
        d.add(Line(x1, y1, x2, y2, strokeColor=colors.black, strokeWidth=.7))
        d.add(Polygon([x2, y2, x2 - 3, y2 + 7, x2 + 3, y2 + 7], fillColor=colors.black))
    box(130, 220, 235, 32, ['浏览器 HTML CSS JavaScript'])
    arrow(247, 220, 247, 195)
    box(130, 150, 235, 45, ['server.py 同源HTTP入口', 'Context 身份 会话 事务'])
    for x, lines in [(0, ['周 users.py', '用户与竞赛']), (170, ['王 teams.py', '队伍与招募']),
                     (340, ['陈 registrations.py', '报名 审核 历史'])]:
        center = x + 77.5
        arrow(247, 150, center, 115)
        box(x, 70, 155, 45, lines)
        arrow(center, 70, 247, 45)
    box(160, 8, 175, 37, ['SQLite 关系数据', '历史事件与成员表单快照'])
    return d


def state_diagram():
    d = Drawing(WIDTH, 145)
    for x, title in [(5, '待审核 pending'), (180, '已驳回 rejected'), (355, '已通过 approved')]:
        d.add(Rect(x, 50, 130, 33, fillColor=colors.white, strokeColor=colors.black, strokeWidth=.7))
        d.add(String(x + 65, 62, title, textAnchor='middle', fontName='Song', fontSize=10))
    d.add(String(4, 130, '队长首次提交后进入待审核', fontName='Song', fontSize=9))
    d.add(String(146, 65, '驳回', fontName='Song', fontSize=9))
    d.add(Line(135, 63, 175, 63, strokeWidth=.7))
    d.add(Polygon([175, 63, 168, 66, 168, 60], fillColor=colors.black))
    d.add(Line(70, 50, 70, 20, strokeWidth=.7))
    d.add(Line(70, 20, 420, 20, strokeWidth=.7))
    d.add(Line(420, 20, 420, 50, strokeWidth=.7))
    d.add(Polygon([420, 50, 417, 43, 423, 43], fillColor=colors.black))
    d.add(String(310, 25, '管理员通过', fontName='Song', fontSize=9))
    d.add(Line(245, 83, 245, 105, strokeWidth=.7))
    d.add(Line(245, 105, 70, 105, strokeWidth=.7))
    d.add(Line(70, 105, 70, 83, strokeWidth=.7))
    d.add(Polygon([70, 83, 67, 90, 73, 90], fillColor=colors.black))
    d.add(String(112, 111, '队长截止前重提', fontName='Song', fontSize=9))
    return d


def escape(text):
    return html.escape(text).replace('`', '')


def build():
    fonts()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    styles = {
        'Body': ParagraphStyle('Body', fontName='Song', fontSize=10.5, leading=16,
                               spaceAfter=6, wordWrap='CJK'),
        'Chapter': ParagraphStyle('Chapter', fontName='Hei', fontSize=18, leading=28,
                                  spaceAfter=18, keepWithNext=True, wordWrap='CJK'),
        'Section': ParagraphStyle('Section', fontName='Hei', fontSize=12.5, leading=20,
                                  spaceBefore=10, spaceAfter=6, keepWithNext=True, wordWrap='CJK'),
        'Cell': ParagraphStyle('Cell', fontName='Song', fontSize=8.3, leading=12.2, wordWrap='CJK'),
        'Small': ParagraphStyle('Small', fontName='Song', fontSize=9, leading=14, wordWrap='CJK', spaceAfter=7),
        'Cover': ParagraphStyle('Cover', fontName='Hei', fontSize=25, leading=38, alignment=TA_CENTER, spaceAfter=22),
        'Center': ParagraphStyle('Center', fontName='Song', fontSize=12, leading=23, alignment=TA_CENTER, spaceAfter=10),
    }
    story = []
    combined = ['# 大学生竞赛信息与组队管理系统课程大作业工程参考稿', '',
                '状态：AI辅助工程参考稿，个人独立初稿、真实对话、最终裁决、个人信息和反思待本人补齐。', '']
    def para(text, kind='Body'):
        return Paragraph(escape(text), styles[kind])
    table_number = {}
    def markdown(text, chapter):
        lines = text.splitlines()
        i = 0
        table_title = '评分记录'
        pending_section = None
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.startswith('# '):
                table_title = line[2:].strip()
                i += 1
                continue
            if line.startswith('##'):
                table_title = re.sub(r'^[\d.一二三四五六七八九十 ]+', '', line.lstrip('#').strip())
                section = para(line.lstrip('#').strip(), 'Section')
                next_line = next((line.strip() for line in lines[i + 1:] if line.strip()), '')
                if next_line.startswith('|'):
                    pending_section = section
                else:
                    story.append(section)
                i += 1
                continue
            if line.startswith('```'):
                language = line[3:]
                code = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code.append(lines[i])
                    i += 1
                raw = '\n'.join(code)
                if language == 'mermaid' and 'flowchart' in raw:
                    story.append(architecture())
                elif language == 'mermaid' and 'stateDiagram' in raw:
                    story.append(state_diagram())
                    story.append(para('图A-1 报名状态流转', 'Small'))
                else:
                    story.append(Paragraph('<br/>'.join(escape(c) for c in code), styles['Small']))
                i += 1
                continue
            if line.startswith('|'):
                rows = []
                while i < len(lines) and lines[i].strip().startswith('|'):
                    cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                    if not all(re.fullmatch(r'[-: ]+', c) for c in cells):
                        rows.append(cells)
                    i += 1
                cols = len(rows[0])
                widths = [WIDTH / cols] * cols
                if cols == 7:
                    widths = [41, 47, 56, 47, 69, 157, WIDTH - 417]
                elif cols == 4:
                    widths = [WIDTH * .18, WIDTH * .22, WIDTH * .38, WIDTH * .22]
                table_number[chapter] = table_number.get(chapter, 0) + 1
                caption = para(f'表{chapter}-{table_number[chapter]} {table_title}', 'Small')
                data = [[Paragraph(escape(cell), styles['Cell']) for cell in row] for row in rows]
                table = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
                table.setStyle(TableStyle([
                    ('GRID', (0, 0), (-1, -1), .5, colors.HexColor('#D9D9D9')),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F0F0F0')),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                    ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ]))
                table.wrap(WIDTH, A4[1])
                first_rows = sum(table._rowHeights[:2])
                heading_height = pending_section.wrap(WIDTH, 100)[1] + 20 if pending_section else 0
                story.append(CondPageBreak(heading_height + caption.wrap(WIDTH, 100)[1] + first_rows + 10))
                if pending_section:
                    story.append(pending_section)
                    pending_section = None
                story.extend([caption, table, Spacer(1, 9)])
                continue
            story.append(para(line))
            i += 1

    story.append(Spacer(1, 42))
    story.append(para('软件工程课程大作业', 'Cover'))
    story.append(para('大学生竞赛信息与组队管理系统', 'Center'))
    story.append(para('工程参考稿 v0.2', 'Center'))
    story.append(Spacer(1, 20))
    for text in ('责任分工 周 用户与竞赛 王 队伍与招募 陈 报名与审核',
                 '学生姓名 班级 学号 学年学期 待本人填写', '整理日期 2026年11月3日'):
        story.append(para(text, 'Center'))
    story.append(Spacer(1, 20))
    story.append(para('本稿整理已实现工程事实与三专项参考内容。各成员必须补齐独立初稿、真实协作对话、个人裁决和反思后形成本人最终作业。技术运行通过不等于老师已经验收。'))
    story.append(Spacer(1, 12))
    markdown('| 评分项目 | 分值 | 得分 |\n| --- | --- | --- |\n| 专项上下文一致性 | 5 | 教师填写 |\n| 需求分析专项 | 25 | 教师填写 |\n| 软件架构设计专项 | 35 | 教师填写 |\n| 需求变更追溯专项 | 20 | 教师填写 |\n| 实践综述 | 10 | 教师填写 |\n| 文档规范性 | 5 | 教师填写 |', '封面')
    story.append(PageBreak())
    story.append(para('目录', 'Section'))
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle('TOC', fontName='Song', fontSize=11, leading=22, spaceBefore=6)]
    story.append(toc)
    story.append(Spacer(1, 24))
    story.append(para('使用说明 本稿按总模板四章组织，参考文献和附录置后。正文的AI采纳标记记录本轮技术实现状态，学生最终裁决仍待签认。完整可编辑来源位于docs目录；个人信息和真实过程证据必须由本人补充。'))

    chapters = [
        ('第一章 需求分析专项', '1', '需求规格说明.md'),
        ('第二章 软件架构设计专项', '2', '架构设计与决策.md'),
        ('第三章 需求变更追溯专项', '3', '需求变更与追溯.md'),
        ('第四章 实践综述', '4', '验收测试记录.md'),
    ]
    for title, chapter, source in chapters:
        story.extend([PageBreak(), para(title, 'Chapter')])
        text = (ROOT / 'docs' / source).read_text(encoding='utf-8')
        references = {'1': '本章依据课程需求分析任务书[3]整理，范围遵循项目说明[1]。',
                      '2': '本章对应软件架构设计专项任务书[4]，草案与学生最终裁决分别记录。',
                      '3': '本章按需求变更追溯任务书[5]提供矩阵与变更评估参考。',
                      '4': '本章按总说明[2]记录工程实践，并核对班级公约[6]。'}
        story.append(para(references[chapter]))
        combined.extend(['# ' + title, '', text, ''])
        markdown(text, chapter)

    story.extend([PageBreak(), para('参考文献', 'Chapter')])
    refs = [
        '[1] 课程教学资料. 课程项目说明[Z]. 2026.',
        '[2] 课程教学资料. 大作业说明[Z]. 2026.',
        '[3] 课程教学资料. 需求分析专项作业任务书[Z]. 2026.',
        '[4] 课程教学资料. 软件架构设计专项任务书[Z]. 2026.',
        '[5] 课程教学资料. 需求变更追溯专项任务书[Z]. 2026.',
        '[6] 课程教学资料. 班级软件开发行为公约 2026试行[Z]. 2026.',
        '[7] 课程教学资料. 大作业报告模板与个人工作清单[Z]. 2026.',
    ]
    for ref in refs:
        story.append(para(ref))
    story.append(para('说明 作者与机构信息在当前资料中未明确，以上按课程资料著录；不虚构出版者或页码。目录中的原文件是课程要求来源；工程结论另以仓库、测试日志和截图支持。'))
    combined.extend(['# 参考文献', '', *refs, ''])

    appendices = [('附录A 课程要求与验收入口', ['课程要求核对.md', '验收指南.md']),
                  ('附录B 三人模块交付', ['周_模块交付.md', '王_模块交付.md', '陈_模块交付.md']),
                  ('附录C AI协作与个人材料', ['AI协作与个人材料.md'])]
    for index, (title, sources) in enumerate(appendices, 1):
        story.extend([PageBreak(), para(title, 'Chapter')])
        combined.extend(['# ' + title, ''])
        for source in sources:
            text = (ROOT / 'docs' / source).read_text(encoding='utf-8')
            if title.startswith('附录B'):
                # 细节已在正文与各模块文件中提供，合并稿保留责任边界和需求摘要。
                if source.startswith('周'):
                    text = text.split('## 输入输出与接口')[0]
                elif source.startswith('王'):
                    text = text.split('## 三 设计与接口')[0]
                elif source.startswith('陈'):
                    text = text.split('## 数据输入与输出')[0]
                text += '\n完整接口、过程设计、专属测试和个人复核要求见项目docs/' + source + '。\n'
            story.append(para(source.removesuffix('.md').replace('_', ' '), 'Section'))
            markdown(text, '附' + str(index))
            combined.extend([text, ''])

    target = OUTPUT / '课程大作业工程参考稿.pdf'
    doc = Report(str(target), pagesize=A4, leftMargin=50, rightMargin=50, topMargin=52, bottomMargin=45,
                 title='大学生竞赛信息与组队管理系统课程大作业工程参考稿', author='课程项目组 AI辅助工程参考')
    doc.addPageTemplates(PageTemplate(id='body', frames=[Frame(50, 45, WIDTH, A4[1] - 97, leftPadding=0,
                                                                rightPadding=0, topPadding=0, bottomPadding=0)],
                                      onPage=page))
    doc.multiBuild(story)
    (ROOT / 'output' / '课程大作业工程参考稿.md').write_text('\n'.join(combined).rstrip() + '\n', encoding='utf-8')
    print(target)


if __name__ == '__main__':
    build()
