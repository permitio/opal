package audit.authorization.context.verify.core.policy_0902

# Auto-generated policy 902 (Rego v1 syntax)
# Package: audit.authorization.context.verify.core

# Metadata
metadata := {
    "policy_id": "0902",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0902_allowed if {
    data.policies.audit.enabled
}
default policy_0902_allowed = false
policy_0902_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
