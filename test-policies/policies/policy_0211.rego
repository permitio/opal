package governance.authorization.context.check.policy_0211

# Auto-generated policy 211 (Rego v1 syntax)
# Package: governance.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0211",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0211_allowed if {
    data.policies.governance.enabled
}
default policy_0211_allowed = false
policy_0211_allowed if {
    input.user.role == "admin"
}
policy_0211_allowed if {
    input.user.active
    input.resource.public
}
