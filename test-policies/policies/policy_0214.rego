package governance.authentication.context.verify.policy_0214

# Auto-generated policy 214 (Rego v1 syntax)
# Package: governance.authentication.context.verify

# Metadata
metadata := {
    "policy_id": "0214",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0214_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0214_allowed if {
    data.policies.governance.enabled
}
