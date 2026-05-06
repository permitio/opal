package compliance.authentication.context.deny.policy_0911

# Auto-generated policy 911 (Rego v1 syntax)
# Package: compliance.authentication.context.deny

# Metadata
metadata := {
    "policy_id": "0911",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0911_allowed = false
policy_0911_allowed if {
    input.user.role == "admin"
}
policy_0911_allowed if {
    data.policies.compliance.enabled
}
policy_0911_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
