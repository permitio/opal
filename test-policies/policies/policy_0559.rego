package audit.validation.policy.verify.policy_0559

# Auto-generated policy 559 (Rego v1 syntax)
# Package: audit.validation.policy.verify

# Metadata
metadata := {
    "policy_id": "0559",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0559_allowed if {
    input.user.active
    input.resource.public
}
policy_0559_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0559_allowed if {
    input.user.role == "admin"
}
