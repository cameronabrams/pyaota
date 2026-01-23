from unittest import TestCase
from pyaota.generator.document import Document, ExamDocument
from pyaota.generator.questionset import QuestionSet

class TestDocument(TestCase):
    def test_document_initialization(self):
        doc = Document("Sample content")
        self.assertEqual(doc.content, "Sample content")

    def test_exam_document_initialization(self):
        specs = {
            'institution': 'Test University',
            'course': 'Test Course',
            'term': 'Fall 2024',
            'examname': 'Midterm Exam',
            'version': 'A',
            'question_list': [{'id': 1, 'type': 'mcq', 'stem': [{'type': 'text', 'text': 'What is 2+2?'}], 'choices': [{'key': 'a', 'text': '3'}, {'key': 'b', 'text': '4'}], 'correct': 'b'}],
            'instructions': 'Please answer all questions.'
        }
        exam_doc = ExamDocument(specs)
        self.assertEqual(exam_doc.institution, 'Test University')
        self.assertEqual(exam_doc.course, 'Test Course')
        self.assertEqual(exam_doc.term, 'Fall 2024')
        self.assertEqual(exam_doc.documentname, 'Midterm Exam')
        self.assertEqual(exam_doc.version, 'A')
        self.assertEqual(len(exam_doc.question_list), 1)
        self.assertEqual(exam_doc.instructions, 'Please answer all questions.')

