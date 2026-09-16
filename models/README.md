# Local model assets

`src/exam_grader/resources/student_number_digit_model.npz` is a bundled,
offline KNN seed model trained from the 198 explicitly accepted PDF digit
annotations. SHA-256:
`a1bbc369a4f25e88583999b95275b993759695bfbbbc8501e359729b129d0a29`.

The model is review-only: it never authorizes identity or auto-accept. It is
trained from one seed sheet/writer and must be treated as an internal seed
model; Vol.8/Vol.9 remain independent held-out evidence. Never download a
model at runtime.
