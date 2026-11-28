//! Request validation that answers in FastAPI's 422 shape.
//!
//! Python gets this from pydantic models. Rust has no equivalent that writes
//! the same error objects, so the rules the cloned routes need are here.

use serde_json::{json, Map, Value};

#[derive(Clone, Copy)]
pub enum Kind {
    Str { min: Option<usize>, max: Option<usize> },
    Int { gt: Option<i64> },
    Bool,
    IntList,
    StrList { max: usize },
    Literal(&'static [&'static str]),
}

pub struct Field {
    pub name: &'static str,
    pub kind: Kind,
    pub required: bool,
    /// `X | None`: null is accepted.
    pub nullable: bool,
}

pub const fn opt(name: &'static str, kind: Kind) -> Field {
    Field { name, kind, required: false, nullable: true }
}

pub const fn req(name: &'static str, kind: Kind) -> Field {
    Field { name, kind, required: true, nullable: false }
}

pub const STR: Kind = Kind::Str { min: None, max: None };
pub const INT: Kind = Kind::Int { gt: None };

fn error(kind: &str, loc: &[Value], msg: impl Into<String>, input: &Value, ctx: Option<Value>) -> Value {
    let mut e = json!({"type": kind, "loc": loc, "msg": msg.into(), "input": input});
    if let (Some(ctx), Some(obj)) = (ctx, e.as_object_mut()) {
        obj.insert("ctx".into(), ctx);
    }
    e
}

fn plural(n: usize, word: &str) -> String {
    format!("{n} {word}{}", if n == 1 { "" } else { "s" })
}

/// pydantic's lax int: ints, whole floats, numeric strings, bools.
fn int(v: &Value, loc: &[Value], gt: Option<i64>) -> Result<Value, Value> {
    let n = match v {
        Value::Bool(b) => *b as i64,
        Value::Number(n) if n.is_i64() => n.as_i64().unwrap_or(0),
        Value::Number(n) => match n.as_f64() {
            Some(f) if f.fract() == 0.0 && f.abs() < 9.0e18 => f as i64,
            _ => {
                return Err(error(
                    "int_from_float",
                    loc,
                    "Input should be a valid integer, got a number with a fractional part",
                    v,
                    None,
                ))
            }
        },
        Value::String(s) => s.trim().parse::<i64>().map_err(|_| {
            error("int_parsing", loc, "Input should be a valid integer, unable to parse string as an integer", v, None)
        })?,
        _ => return Err(error("int_type", loc, "Input should be a valid integer", v, None)),
    };
    match gt {
        Some(gt) if n <= gt => {
            Err(error("greater_than", loc, format!("Input should be greater than {gt}"), v, Some(json!({"gt": gt}))))
        }
        _ => Ok(json!(n)),
    }
}

fn boolean(v: &Value, loc: &[Value]) -> Result<Value, Value> {
    let parsed = match v {
        Value::Bool(b) => Some(*b),
        Value::Number(n) => [false, true].into_iter().find(|b| n.as_f64() == Some(f64::from(u8::from(*b)))),
        Value::String(s) => match s.to_lowercase().as_str() {
            "1" | "true" | "t" | "yes" | "y" | "on" => Some(true),
            "0" | "false" | "f" | "no" | "n" | "off" => Some(false),
            _ => None,
        },
        _ => return Err(error("bool_type", loc, "Input should be a valid boolean", v, None)),
    };
    parsed.map(Value::Bool).ok_or_else(|| {
        error("bool_parsing", loc, "Input should be a valid boolean, unable to interpret input", v, None)
    })
}

fn check(v: &Value, kind: Kind, loc: &[Value], errors: &mut Vec<Value>) -> Option<Value> {
    let result = match kind {
        Kind::Str { min, max } => match v.as_str() {
            None => Err(error("string_type", loc, "Input should be a valid string", v, None)),
            Some(s) => {
                let len = s.chars().count();
                if let Some(min) = min.filter(|min| len < *min) {
                    let msg = format!("String should have at least {}", plural(min, "character"));
                    Err(error("string_too_short", loc, msg, v, Some(json!({"min_length": min}))))
                } else if let Some(max) = max.filter(|max| len > *max) {
                    let msg = format!("String should have at most {}", plural(max, "character"));
                    Err(error("string_too_long", loc, msg, v, Some(json!({"max_length": max}))))
                } else {
                    Ok(v.clone())
                }
            }
        },
        Kind::Int { gt } => int(v, loc, gt),
        Kind::Bool => boolean(v, loc),
        Kind::Literal(allowed) => {
            if v.as_str().is_some_and(|s| allowed.contains(&s)) {
                Ok(v.clone())
            } else {
                let quoted: Vec<String> = allowed.iter().map(|a| format!("'{a}'")).collect();
                let expected = match quoted.split_last() {
                    Some((last, rest)) if !rest.is_empty() => format!("{} or {last}", rest.join(", ")),
                    _ => quoted.join(""),
                };
                Err(error(
                    "literal_error",
                    loc,
                    format!("Input should be {expected}"),
                    v,
                    Some(json!({"expected": expected})),
                ))
            }
        }
        Kind::IntList | Kind::StrList { .. } => {
            let Some(items) = v.as_array() else {
                errors.push(error("list_type", loc, "Input should be a valid list", v, None));
                return None;
            };
            if let Kind::StrList { max } = kind {
                if items.len() > max {
                    let msg = format!(
                        "List should have at most {} after validation, not {}",
                        plural(max, "item"),
                        items.len()
                    );
                    let ctx = json!({"field_type": "List", "max_length": max, "actual_length": items.len()});
                    errors.push(error("too_long", loc, msg, v, Some(ctx)));
                    return None;
                }
            }
            let before = errors.len();
            let item_kind = if matches!(kind, Kind::IntList) { INT } else { STR };
            let cleaned: Vec<Value> = items
                .iter()
                .enumerate()
                .filter_map(|(i, item)| check(item, item_kind, &[loc, &[json!(i)]].concat(), errors))
                .collect();
            return (errors.len() == before).then_some(Value::Array(cleaned));
        }
    };
    match result {
        Ok(value) => Some(value),
        Err(e) => {
            errors.push(e);
            None
        }
    }
}

/// A validated JSON body: only declared fields, coerced as pydantic would.
pub struct Body(pub Map<String, Value>);

impl Body {
    /// The field was sent (pydantic's `model_fields_set`), even as null.
    pub fn has(&self, name: &str) -> bool {
        self.0.contains_key(name)
    }
    pub fn str(&self, name: &str) -> Option<&str> {
        self.0.get(name).and_then(Value::as_str)
    }
    /// Python's `x or None`: an empty string counts as unset.
    pub fn text(&self, name: &str) -> Option<&str> {
        self.str(name).filter(|s| !s.is_empty())
    }
    pub fn int(&self, name: &str) -> Option<i64> {
        self.0.get(name).and_then(Value::as_i64)
    }
    pub fn flag(&self, name: &str) -> Option<bool> {
        self.0.get(name).and_then(Value::as_bool)
    }
    pub fn ints(&self, name: &str) -> Option<Vec<i64>> {
        Some(self.0.get(name)?.as_array()?.iter().filter_map(Value::as_i64).collect())
    }
    pub fn strs(&self, name: &str) -> Vec<String> {
        let items = self.0.get(name).and_then(Value::as_array);
        items.into_iter().flatten().filter_map(|v| v.as_str().map(String::from)).collect()
    }
}

/// Validate `input` against `fields`. `source` is "body" or "query"; a body
/// model with `extra="forbid"` passes `forbid_extra`. Err holds the 422 detail.
pub fn validate(input: &Value, fields: &[Field], source: &str, forbid_extra: bool) -> Result<Body, Value> {
    let root = [json!(source)];
    let Some(given) = input.as_object() else {
        let msg = "Input should be a valid dictionary or object to extract fields from";
        return Err(json!([error("model_attributes_type", &root, msg, input, None)]));
    };
    let mut errors = Vec::new();
    let mut clean = Map::new();
    for field in fields {
        let loc = [json!(source), json!(field.name)];
        match given.get(field.name) {
            None if field.required => errors.push(error("missing", &loc, "Field required", input, None)),
            None => {}
            Some(Value::Null) if field.nullable => {
                clean.insert(field.name.into(), Value::Null);
            }
            Some(value) => {
                if let Some(value) = check(value, field.kind, &loc, &mut errors) {
                    clean.insert(field.name.into(), value);
                }
            }
        }
    }
    if forbid_extra {
        for (name, value) in given.iter().filter(|(name, _)| !fields.iter().any(|f| f.name == name.as_str())) {
            errors.push(error(
                "extra_forbidden",
                &[json!(source), json!(name)],
                "Extra inputs are not permitted",
                value,
                None,
            ));
        }
    }
    if errors.is_empty() {
        Ok(Body(clean))
    } else {
        Err(Value::Array(errors))
    }
}
