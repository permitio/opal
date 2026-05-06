package compliance.validation.resource.verify.logic.policy_0855

# Auto-generated policy 855 (Rego v1 syntax)
# Package: compliance.validation.resource.verify.logic

# Metadata
metadata := {
    "policy_id": "0855",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0855_allowed if {
    input.user.role == "admin"
}
policy_0855_allowed if {
    input.user.active
    input.resource.public
}
