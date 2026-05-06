package compliance.authentication.resource.verify.utils.policy_0939

# Auto-generated policy 939 (Rego v1 syntax)
# Package: compliance.authentication.resource.verify.utils

# Metadata
metadata := {
    "policy_id": "0939",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0939_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0939_allowed if {
    input.user.active
    input.resource.public
}
