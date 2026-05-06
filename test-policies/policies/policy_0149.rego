package audit.authentication.user.verify.policy_0149

# Auto-generated policy 149 (Rego v1 syntax)
# Package: audit.authentication.user.verify

# Metadata
metadata := {
    "policy_id": "0149",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0149_allowed if {
    data.policies.audit.enabled
}
policy_0149_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
