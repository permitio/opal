package access.authorization.user.check.logic.policy_0275

# Auto-generated policy 275 (Rego v1 syntax)
# Package: access.authorization.user.check.logic

# Metadata
metadata := {
    "policy_id": "0275",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0275_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0275_allowed if {
    data.policies.access.enabled
}
