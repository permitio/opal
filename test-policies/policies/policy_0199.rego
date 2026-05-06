package risk.validation.action.verify.data.policy_0199

# Auto-generated policy 199 (Rego v1 syntax)
# Package: risk.validation.action.verify.data

# Metadata
metadata := {
    "policy_id": "0199",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0199_allowed if {
    data.policies.risk.enabled
}
policy_0199_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0199_allowed if {
    input.user.role == "admin"
}
