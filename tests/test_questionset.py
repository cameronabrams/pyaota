from unittest import TestCase
from pyaota.generator.questionset import QuestionSet

class TestQuestionSet(TestCase):

    def test_questionset_loading(self):
        # Assuming we have a sample YAML file for testing
        sample_yaml = """
        topics:
          - Math
          - Science
        questions:
          - id: 1
            type: mcq
            topic: Math
            stem: 
             - type: text
               text: What is 2+2?
            choices:
              - key: a
                text: 3
              - key: b
                text: 4
            correct: b
          - id: 2
            type: tf
            topic: Science
            stem: 
             - type: text
               text: The Earth is flat.
            answer: False
        """
        with open('test_questions.yaml', 'w') as f:
            f.write(sample_yaml)

        qs = QuestionSet(['test_questions.yaml'])
        self.assertIn('Math', qs.apparent_topics)
        self.assertIn('Science', qs.apparent_topics)
        self.assertEqual(len(qs.raw_question_list), 2)