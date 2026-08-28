"""Adapters turn an existing tailoring pipeline's output into resume.yaml data
(a plain dict, same shape schema.validate() expects). An adapter never touches
the pipeline that produced its input — it only reads the finished file."""
