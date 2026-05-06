package access.authorization.user.verify.policy_0696

# Auto-generated policy 696 (Rego v1 syntax)
# Package: access.authorization.user.verify

# Metadata
metadata := {
    "policy_id": "0696",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0696_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0696_allowed if {
    data.policies.access.enabled
}
default policy_0696_allowed = false
