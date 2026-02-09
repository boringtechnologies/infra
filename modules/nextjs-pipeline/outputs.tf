output "pipeline_name" {
  value = var.enable_cicd ? aws_codepipeline.pipeline[0].name : ""
}

output "codebuild_project_name" {
  value = var.enable_cicd ? aws_codebuild_project.build[0].name : ""
}