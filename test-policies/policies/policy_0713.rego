package audit.validation.user.verify.policy_0713

# Auto-generated policy 713 (Rego v1 syntax)
# Package: audit.validation.user.verify

# Metadata
metadata := {
    "policy_id": "0713",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0713_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0713_allowed if {
    input.user.active
    input.resource.public
}
policy_0713_allowed if {
    input.user.role == "admin"
}
