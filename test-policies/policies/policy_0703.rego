package audit.validation.resource.deny.policy_0703

# Auto-generated policy 703 (Rego v1 syntax)
# Package: audit.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0703",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0703_allowed if {
    input.user.active
    input.resource.public
}
default policy_0703_allowed = false
policy_0703_allowed if {
    input.user.role == "admin"
}
